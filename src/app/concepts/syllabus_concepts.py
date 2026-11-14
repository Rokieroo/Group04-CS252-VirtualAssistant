"""Concepts of a whole course from its syllabus (issue #97).

Three readers, merged into one list:

- the weekly schedule: each topic line split into its listed parts;
- the learning outcomes (CLOs): the items they enumerate in parentheses;
- with a live model, the page-window extractor of ``from_pages`` over the whole syllabus.

Every concept is *verified or dropped* (as the syllabus parser, #59): the words of its
title must appear on the page it cites, and it keeps that line as its quote. Nothing
here may name a concept of its own; titles come only from the syllabus text.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from app.llm import FakeLLM, LLMClient

from .from_pages import DECORATIVE, extract_concepts
from .normalize import _clean_title, _unique_slug, comparison_key, slugify

MERGE_SIMILARITY = 0.85
QUOTE_CHARS = 200
_ADMIN = DECORATIVE | {"orientation", "review", "course overview", "wrap up"}
# A schedule line naming an assessment is a milestone (``assessments``), not a concept.
_ASSESSMENT = {"midterm", "final", "exam", "quiz", "test"}


def split_outside_parens(text: str, delimiters: tuple[str, ...] = (",", ";")) -> list[str]:
    """Split on any delimiter that is not inside parentheses."""
    parts, current, depth, i = [], [], 0, 0
    while i < len(text):
        delimiter = next((d for d in delimiters if depth == 0 and text.startswith(d, i)), None)
        if delimiter:
            parts.append("".join(current))
            current, i = [], i + len(delimiter)
            continue
        depth = max(0, depth + {"(": 1, ")": -1}.get(text[i], 0))
        current.append(text[i])
        i += 1
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def topic_parts(topic: str) -> list[str]:
    """``"Stacks, Queues, and Parsing."`` -> the three listed parts.

    A part joined only by "and" ("Divide and Conquer", "Tree Balancing and AVL
    Rotations") is kept whole: without a list around it, "and" is often part of a name.
    A heading before a colon is a concept of its own.
    """
    head, _, rest = topic.partition(":") if ":" in topic else ("", "", topic)
    parts = [head] if head.strip() else []
    for part in split_outside_parens(rest.strip().rstrip(".")):
        parts.append(part[4:] if part.casefold().startswith("and ") else part)
    return [p.strip(" .") for p in parts if p.strip(" .")]


def enumerated(outcome: str) -> list[str]:
    """Items an outcome lists in parentheses: ``"(arrays, linked lists)"`` -> both."""
    items: list[str] = []
    depth, start = 0, 0
    for i, ch in enumerate(outcome):
        if ch == "(":
            depth += 1
            start = i + 1 if depth == 1 else start
        elif ch == ")" and depth:
            depth -= 1
            inner = split_outside_parens(outcome[start:i]) if depth == 0 else []
            if len(inner) > 1:  # "(BFS)" is an abbreviation, not a list
                items += [item.removeprefix("and ").strip() for item in inner]
    return items


def _words(text: str) -> list[str]:
    return comparison_key(text).split()


def _contains(text: str, title: str) -> bool:
    words, key = _words(title), f" {comparison_key(text)} "
    return bool(words) and all(f" {w} " in key for w in words)


def _grounded(title: str, page_text: str) -> str | None:
    """The line of ``page_text`` that holds every word of ``title``, else None.

    A line and the next are also tried together: PDF text wraps long topics.
    """
    lines = page_text.splitlines()
    spans = [*lines, *(f"{a} {b}" for a, b in pairwise(lines))]
    line = next((span for span in spans if _contains(span, title)), None)
    return None if line is None else " ".join(line.split())[:QUOTE_CHARS]


def merge_similar_concepts(
    concepts: list[dict[str, Any]],
    *,
    encoder: Any | None = None,
    threshold: float = MERGE_SIMILARITY,
) -> list[dict[str, Any]]:
    """Merge concepts whose title embeddings have cosine similarity >= ``threshold``.

    Embeddings put "BFS" next to "DFS", so a merge also needs one normalized word in
    common ("BFS" and "Breadth-First Search (BFS)"). The earlier concept absorbs the
    later one: pages, CLO codes and its title (as an alias) are kept. Without an
    encoder, or if it fails, nothing is merged. Inputs are not modified.
    """
    if encoder is None or len(concepts) < 2:
        return concepts
    titles = [c["title"] for c in concepts]
    try:
        encoder.prepare(titles)
        vectors = [encoder.encode(t) for t in titles]
    except Exception:  # noqa: BLE001 - embeddings are optional; never lose concepts
        return concepts

    kept: list[tuple[dict[str, Any], list[float]]] = []
    for concept, vector in zip(concepts, vectors, strict=True):
        target = next(
            (k for k, v in kept
             if sum(a * b for a, b in zip(v, vector, strict=True)) >= threshold
             and set(_words(k["title"])) & set(_words(concept["title"]))),
            None,
        )
        if target is None:
            kept.append(({**concept, "aliases": list(concept.get("aliases", []))}, vector))
        else:
            _absorb(target, concept)
    return [concept for concept, _ in kept]


def _absorb(into: dict[str, Any], other: dict[str, Any]) -> None:
    into["week"] = min(into["week"], other["week"])
    into["source_pages"] = sorted(set(into["source_pages"]) | set(other["source_pages"]))
    into["clo_codes"] = list(dict.fromkeys([*into["clo_codes"], *other["clo_codes"]]))
    known = {comparison_key(t) for t in [into["title"], *into["aliases"]]}
    for alias in [other["title"], *other.get("aliases", [])]:
        if comparison_key(alias) not in known:
            known.add(comparison_key(alias))
            into["aliases"].append(alias)


def _candidates(parsed: dict[str, Any], pages: list[str], llm: LLMClient | None):
    """(title, week, page, CLO codes, is_mention) proposals, before grounding.

    Schedule parts come first. A concept read elsewhere is a *mention*: it takes the
    first week whose topics name it, and joins a schedule concept that contains it.
    """
    weeks = [(int(r.get("week") or 1), " ".join(map(str, r.get("topics", []))))
             for r in parsed.get("weeks", [])]
    first = min((week for week, _ in weeks), default=1)

    def week_of(title: str) -> int:
        return min((week for week, text in weeks if _contains(text, title)), default=first)

    for row in parsed.get("weeks", []):
        week, page = int(row.get("week") or 1), int(row.get("source_page") or 1)
        for topic in row.get("topics", []):
            for part in topic_parts(str(topic)):
                yield part, week, page, [], False
    for outcome in parsed.get("outcomes", []):
        code = str(outcome.get("code") or "").upper()
        page = int(outcome.get("source_page") or 1)
        for item in enumerated(str(outcome.get("text") or "")):
            yield item, week_of(item), page, [code] if code else [], True
    if llm is not None and not isinstance(llm, FakeLLM):
        for concept in extract_concepts(llm, pages):
            title = concept["title"]
            yield title, week_of(title), concept["source_pages"][0], [], True


def extract_course_concepts(
    parsed: dict[str, Any],
    pages: list[str],
    *,
    llm: LLMClient | None = None,
    encoder: Any | None = None,
) -> list[dict[str, Any]]:
    """Every grounded concept of the course, duplicates merged, slugs unique.

    ``parsed`` is a parsed syllabus (``weeks``, ``outcomes``); ``pages[0]`` is page 1.
    Each concept has ``source_page`` (its first citation), ``source_pages``, ``quote``
    (the cited line), ``week``, ``clo_codes`` and ``aliases``.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for raw, week, page, codes, mention in _candidates(parsed, pages, llm):
        title = _clean_title(raw)
        key = comparison_key(title)
        if not key or key in _ADMIN or key.split()[0] in _ASSESSMENT:
            continue
        if not 1 <= page <= len(pages):
            continue
        quote = _grounded(title, pages[page - 1])
        if quote is None:
            continue  # verify or drop
        concept = {"title": title, "week": week, "source_page": page, "source_pages": [page],
                   "quote": quote, "clo_codes": codes, "aliases": []}
        # "BFS" in a CLO is the schedule's "Breadth-First Search (BFS)".
        same = by_key.get(key) or (mention and next(
            (c for c in by_key.values() if _contains(c["title"], title)), None))
        if same:
            _absorb(same, concept)
        else:
            by_key[key] = concept

    concepts = merge_similar_concepts(list(by_key.values()), encoder=encoder)
    used: set[str] = set()
    return [{**c, "slug": _unique_slug(slugify(c["title"]), used)} for c in concepts]


__all__ = [
    "MERGE_SIMILARITY",
    "enumerated",
    "extract_course_concepts",
    "merge_similar_concepts",
    "split_outside_parens",
    "topic_parts",
]
