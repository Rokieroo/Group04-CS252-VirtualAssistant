"""Concept extraction from per-page slide text (issue #9, spec 10.1).

Pages are read in 20-page windows, up to four at once; each window asks the LLM for 0-5
concepts, duplicates are merged, and a deck with too many candidates is consolidated.
Slide text is data only, never instructions (spec 10.6).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from app.llm import LLMClient, RetryableError

log = logging.getLogger("app.concepts")

PROMPTS = Path(__file__).parent / "prompts"
EXTRACT_PROMPT = "extract_v3"
CONSOLIDATE_PROMPT = "consolidate_v1"
# 20 pages, no overlap: windows run in parallel, so each page is read exactly once and a
# concept split across two windows is joined by merge(). 20 pages is few enough that the
# model reads each one closely (8 calls for the 146-page Week 1 deck).
WINDOW, STEP = 20, 20
PARALLEL = 4  # windows in flight at once
SIMILAR_TITLE = 0.9
MAX_CONCEPTS = 20
BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
# Backstop for the prompt rule; compared after normalize().
DECORATIVE = {"q a", "content", "contents", "agenda", "outline", "questions", "thank you"}
_BLOCK_TAG = re.compile(
    r"</?\s*(slide_text|known_concepts|previous_concepts|candidates|concept)\s*>", re.IGNORECASE)

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
                    "source_pages": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["slug", "title", "summary", "bloom_level", "source_pages"],
            },
        }
    },
    "required": ["concepts"],
}
CONSOLIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "merge": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["slug"],
            },
        }
    },
    "required": ["concepts"],
}


def windows(page_count: int) -> list[list[int]]:
    """1-based page numbers per window; the last window always reaches the last page."""
    result = []
    for start in range(1, page_count + 1, STEP):
        result.append(list(range(start, min(start + WINDOW, page_count + 1))))
        if start + WINDOW > page_count:
            break
    return result


def slugify(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    ascii_text = ascii_text.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80].strip("-")


def normalize(title: str) -> str:
    return slugify(title).replace("-", " ")


def parse_concepts(answer: str, pages: set[int]) -> list[dict]:
    """Validate one window's JSON answer; raises ValueError when the answer is unusable.

    Single concepts that break a rule are dropped, and pages outside the window are
    removed so every citation points at text the model was actually shown.
    """
    data = json.loads(answer)
    if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
        # ValueError, like bad JSON, so the caller skips just this window.
        raise ValueError('expected {"concepts": [...]}')  # noqa: TRY004
    concepts = []
    for raw in data["concepts"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("source_pages"), list):
            continue
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        slug = slugify(str(raw.get("slug") or "")) or slugify(title)
        cited = sorted({p for p in raw["source_pages"] if type(p) is int and p in pages})
        if not (title and summary and slug and cited) or normalize(title) in DECORATIVE:
            continue
        bloom = raw.get("bloom_level")
        concepts.append({
            "slug": slug,
            "title": title[:120],
            "summary": summary[:500],
            "bloom_level": bloom if bloom in BLOOM_LEVELS else "understand",
            "source_pages": cited,
        })
    return concepts


def merge(concepts: list[dict], into: list[dict] | None = None) -> list[dict]:
    """Merge by equal slug or near-equal title; the concept seen first keeps its fields."""
    merged = [dict(c) for c in into or []]
    for concept in concepts:
        same = next((m for m in merged if m["slug"] == concept["slug"] or SequenceMatcher(
            None, normalize(m["title"]), normalize(concept["title"])).ratio() >= SIMILAR_TITLE),
            None)
        if same is None:
            merged.append(dict(concept))
        else:
            same["source_pages"] = sorted(set(same["source_pages"]) | set(concept["source_pages"]))
    return merged


def extract_concepts(llm: LLMClient, pages: list[str], visuals: list[str] | None = None,
                     previous: list[dict] | None = None) -> list[dict]:
    """Propose concepts for one deck; ``pages[0]`` is page 1.

    ``visuals`` holds the vision model's note per page (see visual.py), "" for none.
    ``previous`` holds concepts proposed earlier for this deck: each window revises the
    ones citing its pages instead of starting over.
    Windows run PARALLEL at a time; a batch is told the concepts found by earlier batches.
    """
    system = _prompt(EXTRACT_PROMPT)
    visuals = visuals or [""] * len(pages)
    previous = previous or []
    found: list[dict] = []

    def read_window(numbers: list[int], known: str) -> list[dict]:
        slides = "\n".join(
            f"[Page {n}] {pages[n - 1]}"
            + (f"\n[Page {n} visual] {visuals[n - 1]}" if visuals[n - 1] else "")
            for n in numbers)
        earlier = "\n".join(f"{c['slug']} | {c['title']} | {c['summary']} | pages "
                            f"{c['source_pages']}" for c in previous
                            if set(c["source_pages"]) & set(numbers))
        prompt = (f"<known_concepts>\n{_data(known)}\n</known_concepts>\n"
                  + (f"<previous_concepts>\n{_data(earlier)}\n</previous_concepts>\n"
                     if earlier else "")
                  + f"<slide_text>\n{_data(slides)}\n</slide_text>")
        try:
            answer = llm.complete(prompt, system=system, json_schema=EXTRACT_SCHEMA,
                                  max_tokens=8192, temperature=0.2).text  # thinking counts
            return parse_concepts(answer, set(numbers))
        except (ValueError, RetryableError) as exc:  # bad JSON, or quota/network after retries
            log.warning("concepts: skipped pages %d-%d: %s", numbers[0], numbers[-1], exc)
            return []

    readable = [numbers for numbers in windows(len(pages))
                if any(pages[n - 1].strip() or visuals[n - 1] for n in numbers)]
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for start in range(0, len(readable), PARALLEL):
            known = "\n".join(f"- {c['slug']}: {c['title']}"
                              for c in merge(found, previous)) or "(none yet)"
            batch = readable[start:start + PARALLEL]
            for concepts in pool.map(read_window, batch, [known] * len(batch)):
                found = merge(concepts, found)  # in page order, so merging is deterministic
    if len(found) > MAX_CONCEPTS:
        found = consolidate(llm, found)
    return sorted(found, key=lambda c: c["source_pages"][0])


def consolidate(llm: LLMClient, candidates: list[dict]) -> list[dict]:
    """Ask the LLM to keep the core concepts; pages are always unioned in code, never by the LLM."""
    by_slug = {c["slug"]: c for c in candidates}
    listing = "\n".join(f"{c['slug']} | {c['title']} | {c['summary']}" for c in candidates)
    system = _prompt(CONSOLIDATE_PROMPT).replace("{max_concepts}", str(MAX_CONCEPTS))
    kept: list[dict] = []
    used: set[str] = set()
    try:
        answer = llm.complete(f"<candidates>\n{_data(listing)}\n</candidates>", system=system,
                              json_schema=CONSOLIDATE_SCHEMA, max_tokens=8192,
                              temperature=0.2).text
        for group in json.loads(answer)["concepts"]:
            members = [by_slug[s] for s in [group["slug"], *group.get("merge", [])]
                       if s in by_slug and s not in used]
            if not members or members[0]["slug"] != group["slug"]:
                continue  # unknown or already used primary slug
            used.update(m["slug"] for m in members)
            kept.append({**members[0], "source_pages": sorted(
                {p for m in members for p in m["source_pages"]})})
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("concepts: consolidation failed, keeping widest concepts: %s", exc)
        kept = []
    if not kept:
        kept = sorted(candidates, key=lambda c: -len(c["source_pages"]))
    return kept[:MAX_CONCEPTS]


def save_concepts(db, course_id: str, concepts: list[dict]) -> list[dict]:
    """Store proposals as unconfirmed; an existing concept gains pages, and when a proposal
    revises it (same slug) while still unconfirmed, also its title, summary and bloom level.
    A confirmed concept keeps the user's wording.

    ``db`` is a SQLAlchemy Session or Connection; the caller commits.
    shortcut: source_pages has no file name, so two decks of one course share page numbers;
    add a source_file column when a course holds more than one deck.
    """
    rows = db.execute(text(
        "SELECT id, slug, title, summary, bloom_level, source_pages, confirmed FROM concepts "
        "WHERE course_id = :course_id"), {"course_id": course_id}).mappings()
    stored = [{**row, "source_pages": json.loads(row["source_pages"] or "[]")} for row in rows]
    revised = {c["slug"]: c for c in concepts}
    result = merge(concepts, stored)
    for concept in result:
        if "id" in concept and not concept["confirmed"] and concept["slug"] in revised:
            new = revised[concept["slug"]]
            concept.update(title=new["title"], summary=new["summary"],
                           bloom_level=new["bloom_level"])
        params = {**concept, "course_id": course_id,
                  "source_pages": json.dumps(concept["source_pages"])}
        if "id" in concept:
            db.execute(text(
                "UPDATE concepts SET title = :title, summary = :summary, "
                "bloom_level = :bloom_level, source_pages = :source_pages WHERE id = :id"),
                params)
        else:
            concept["id"] = params["id"] = str(uuid4())
            db.execute(text(
                "INSERT INTO concepts (id, course_id, slug, title, summary, bloom_level, "
                "source_pages, confirmed) VALUES (:id, :course_id, :slug, :title, :summary, "
                ":bloom_level, :source_pages, 0)"), params)
    return result


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def _data(value: str) -> str:
    """Strip our block tags so slide text cannot close its data block early."""
    return _BLOCK_TAG.sub("", value)
