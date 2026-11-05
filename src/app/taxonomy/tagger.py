"""Subject tagging (issue #99): rules first, then embeddings, the LLM only when unsure.

A label is a ``Tag`` (slug, confidence, method). The cascade stops for an item as
soon as one of its labels reaches ``REVIEW_CONFIDENCE``, so embeddings see only what
the rules could not settle and the LLM only what neither could. Labels below that
confidence are kept for a reviewer to confirm (#101).

Nodes and resources go through the same cascade, so their labels can be compared
(#102). Every item is embedded when an embedder is given: the vector is returned
for the caller to store and reuse in hybrid retrieval.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.llm import Embedder, LLMClient, RetryableError
from app.llm.blocks import BLOCKS
from app.taxonomy.rules import RuleMatcher, find_course_codes
from app.taxonomy.tree import Taxonomy, load_taxonomy
from app.vetting.judge import strip_commands

log = logging.getLogger("app.taxonomy")

REVIEW_CONFIDENCE = 0.6  # below: a reviewer confirms the label before #102 relies on it
MIN_CONFIDENCE = 0.3  # below: noise, not stored
MAX_TAGS = 3
TITLE_CONFIDENCE = 0.9  # a taxonomy term in the item's own title
CONTEXT_CONFIDENCE = 0.65  # only in its outcomes, description or course; used when the title is silent
CODE_CONFIDENCE = 0.85  # the course code belongs to the subject
DEPARTMENT_CONFIDENCE = 0.5  # a faculty name narrows the field, not the topic
HIT_BONUS = 0.03  # per extra distinct term for the same entry
MAX_RULE_CONFIDENCE = 0.95
# shortcut: a straight line from cosine to confidence, fitted on gemini-embedding-001
# (768 dims) over the 110 eval resources: the nearest topic was right for 83% of them
# from 0.78 up and 91% from 0.83 up, so 0.83 maps to REVIEW_CONFIDENCE. Refit with
# eval/run_subjects.py --live when LLM_EMBEDDING_MODEL changes.
EMBED_FLOOR, EMBED_CEIL = 0.78, 0.88
EMBED_TOP = 1  # the runner-up was rarely right
LLM_BATCH = 20  # items per prompt: the free tier allows ~20 calls a day
LLM_MAX_CONFIDENCE = 0.9  # self-reported confidence is not calibrated; never above rules
MAX_TEXT_CHARS = 1500
TAGGER_PROMPT = "tagger_v1"
PROMPTS = Path(__file__).parent / "prompts"
_EXTENSION = re.compile(r"\.(?:html?|php|aspx?|pdf)$", re.IGNORECASE)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "subjects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slug": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["slug", "confidence"],
                        },
                    },
                },
                "required": ["id", "subjects"],
            },
        }
    },
    "required": ["items"],
}


@dataclass(frozen=True)
class Tag:
    slug: str
    confidence: float
    method: str  # rule | embedding | llm | manual

    @property
    def needs_review(self) -> bool:
        return self.confidence < REVIEW_CONFIDENCE


@dataclass(frozen=True)
class NodeText:
    """A roadmap node (#60). Its title decides; outcomes, the topics a milestone
    covers and the course name only speak when the title matches nothing."""

    title: str
    outcomes: tuple[str, ...] = ()
    course: str = ""  # course title, may carry its code ("CSC10014 Problem framing")
    covers: tuple[str, ...] = ()  # titles of the topics a milestone covers
    level: str = "university"  # k12 | undergrad | grad | university


@dataclass(frozen=True)
class ResourceText:
    """A resource as stored: title and URL decide, the rest is context."""

    title: str
    url: str = ""
    description: str = ""
    course_code: str = ""  # catalog course code, e.g. "6.006"
    course_title: str = ""
    department: str = ""
    level: str = "university"


@dataclass(frozen=True)
class Tagging:
    tags: tuple[Tag, ...]
    embedding: tuple[float, ...] | None = None
    complete: bool = True  # False: a stage this item needed failed; tag it again later


@dataclass(frozen=True)
class _Item:
    title: str
    context: str
    codes: tuple[str, ...]
    department: str
    level: str
    own_codes: bool  # True: the code is the item's own course (a catalog unit), not context

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.context}".strip()[:MAX_TEXT_CHARS]


class Tagger:
    def __init__(self, taxonomy: Taxonomy | None = None, *, embedder: Embedder | None = None,
                 llm: LLMClient | None = None):
        self.taxonomy = taxonomy or load_taxonomy()
        self.rules = RuleMatcher(self.taxonomy)
        self.embedder = embedder
        self.llm = llm
        self._subject_vectors: dict[str, list[float]] | None = None

    def tag_nodes(self, nodes: Sequence[NodeText]) -> list[Tagging]:
        return self._tag([
            _Item(node.title, "\n".join((*node.outcomes, *node.covers, node.course)),
                  find_course_codes(node.course), "", node.level, own_codes=False)
            for node in nodes
        ])

    def tag_resources(self, resources: Sequence[ResourceText]) -> list[Tagging]:
        return self._tag([
            _Item(f"{resource.title}\n{_url_words(resource.url)}",
                  f"{resource.description}\n{resource.course_title}",
                  tuple(code for code in (resource.course_code.strip(),
                                          *find_course_codes(resource.course_title)) if code),
                  resource.department, resource.level, own_codes=True)
            for resource in resources
        ])

    def _tag(self, items: list[_Item]) -> list[Tagging]:
        found = [self._rule(item) for item in items]
        vectors = self._embed([item.text for item in items])
        failed = set(range(len(items))) if vectors is None and self.embedder else set()
        if vectors is not None:
            for index, item in enumerate(items):
                if not _sure(found[index]):
                    _merge(found[index], self._nearest(vectors[index], item.level))
        unsure = [index for index in range(len(items)) if not _sure(found[index])]
        if unsure and self.llm is not None:
            answers = self._ask([items[index] for index in unsure])
            for index, tags in zip(unsure, answers):
                if tags is None:
                    failed.add(index)
                else:
                    _merge(found[index], tags)
        return [
            Tagging(self._best(found[index]),
                    tuple(vectors[index]) if vectors is not None else None,
                    index not in failed)
            for index in range(len(items))
        ]

    def _rule(self, item: _Item) -> dict[str, Tag]:
        tags: dict[str, Tag] = {}
        hits = self.rules.terms(item.title)
        title_silent = not hits
        base = CONTEXT_CONFIDENCE if title_silent else TITLE_CONFIDENCE
        if title_silent:
            hits = self.rules.terms(item.context)
        for slug, count in hits.items():
            confidence = min(MAX_RULE_CONFIDENCE, base + HIT_BONUS * (count - 1))
            _merge(tags, [Tag(slug, confidence, "rule")])
        if item.own_codes or title_silent:
            _merge(tags, [Tag(slug, CODE_CONFIDENCE, "rule")
                          for slug in self.rules.codes(item.codes)])
        if not tags and item.department:
            _merge(tags, [Tag(slug, DEPARTMENT_CONFIDENCE, "rule")
                          for slug in self.rules.departments(item.department)])
        return self._allowed(tags, item.level)

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        if self.embedder is None or not texts:
            return None
        try:
            if self._subject_vectors is None:
                entries = [subject for subject in self.taxonomy if subject.depth != "field"]
                vectors = self.embedder.embed([_describe(subject) for subject in entries])
                self._subject_vectors = {s.slug: v for s, v in zip(entries, vectors)}
            return self.embedder.embed(texts)
        except RetryableError as exc:
            log.warning("taxonomy: embedding failed: %s", exc)
            return None

    def _nearest(self, vector: list[float], level: str) -> list[Tag]:
        fields = self.taxonomy.fields_for(level)
        scored = sorted(
            ((_cosine(vector, other), slug) for slug, other in (self._subject_vectors or {}).items()
             if self.taxonomy[slug].field in fields),
            reverse=True,
        )
        return [Tag(slug, _embedding_confidence(similarity), "embedding")
                for similarity, slug in scored[:EMBED_TOP] if similarity >= EMBED_FLOOR]

    def _ask(self, items: list[_Item]) -> list[list[Tag] | None]:
        """One prompt per batch of items of the same level; None marks a failed batch."""
        answers: list[list[Tag] | None] = [None] * len(items)
        by_level: dict[frozenset[str], list[int]] = {}
        for index, item in enumerate(items):
            by_level.setdefault(self.taxonomy.fields_for(item.level), []).append(index)
        for fields, indexes in by_level.items():
            allowed = [s for s in self.taxonomy if s.depth != "field" and s.field in fields]
            for start in range(0, len(indexes), LLM_BATCH):
                batch = indexes[start:start + LLM_BATCH]
                tags = self._ask_batch(allowed, [items[index] for index in batch])
                for index, item_tags in zip(batch, tags or [None] * len(batch)):
                    answers[index] = item_tags
        return answers

    def _ask_batch(self, allowed: list, items: list[_Item]) -> list[list[Tag]] | None:
        prompt = (
            BLOCKS.wrap("taxonomy", "\n".join(f"{s.slug}: {s.name} / {s.name_vi}" for s in allowed))
            + "\n"
            + BLOCKS.wrap("tag_items", "\n\n".join(
                f"[{number}] {strip_commands(item.text)}" for number, item in enumerate(items, 1)))
        )
        try:
            answer = self.llm.complete(
                prompt,
                system=(PROMPTS / f"{TAGGER_PROMPT}.txt").read_text(encoding="utf-8"),
                json_schema=SCHEMA,
                max_tokens=256 * len(items),
                temperature=0.0,
            ).text
            return parse_answer(answer, len(items), {s.slug for s in allowed})
        except (RetryableError, ValueError) as exc:
            log.warning("taxonomy: LLM tagging failed: %s", exc)
            return None

    def _allowed(self, tags: dict[str, Tag], level: str) -> dict[str, Tag]:
        fields = self.taxonomy.fields_for(level)
        return {slug: tag for slug, tag in tags.items() if self.taxonomy[slug].field in fields}

    def _best(self, tags: dict[str, Tag]) -> tuple[Tag, ...]:
        """Most confident first. A subject goes when one of its topics is at least as
        sure: the topic says more, and the subject is implied by the tree."""
        covered = {ancestor for tag in tags.values() for ancestor in self.taxonomy.ancestors(tag.slug)
                   if tags.get(ancestor) and tag.confidence >= tags[ancestor].confidence}
        kept = [tag for slug, tag in tags.items()
                if slug not in covered and tag.confidence >= MIN_CONFIDENCE]
        return tuple(sorted(kept, key=lambda tag: (-tag.confidence, tag.slug))[:MAX_TAGS])


def parse_answer(answer: str, count: int, allowed: set[str]) -> list[list[Tag]]:
    """Labels per item from the LLM's JSON; unknown slugs and items are dropped.

    Raises ValueError when the answer is not JSON, so the caller can retry later.
    """
    data = json.loads(answer)
    tags: list[list[Tag]] = [[] for _ in range(count)]
    for row in data.get("items", []) if isinstance(data, dict) else []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            continue
        number = row["id"]
        if not 1 <= number <= count:
            continue
        for label in (row.get("subjects") or [])[:MAX_TAGS]:
            if not isinstance(label, dict) or label.get("slug") not in allowed:
                continue
            try:
                confidence = float(label.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            if math.isfinite(confidence):
                tags[number - 1].append(Tag(label["slug"],
                                            min(LLM_MAX_CONFIDENCE, max(0.0, confidence)), "llm"))
    return tags


def _sure(tags: dict[str, Tag]) -> bool:
    return any(not tag.needs_review for tag in tags.values())


def _merge(tags: dict[str, Tag], new: list[Tag]) -> None:
    for tag in new:
        if tag.slug not in tags or tag.confidence > tags[tag.slug].confidence:
            tags[tag.slug] = tag


def _describe(subject) -> str:
    return f"{subject.name} ({subject.name_vi}): {', '.join(subject.keywords)}"


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _embedding_confidence(similarity: float) -> float:
    """EMBED_FLOOR -> MIN_CONFIDENCE, EMBED_CEIL and above -> 0.9."""
    share = (min(similarity, EMBED_CEIL) - EMBED_FLOOR) / (EMBED_CEIL - EMBED_FLOOR)
    return round(MIN_CONFIDENCE + share * (0.9 - MIN_CONFIDENCE), 4)


def _url_words(url: str) -> str:
    """The readable part of a URL: host without www and TLD, then the path, with
    CamelCase split ("/bliki/CleanCode.html" -> "bliki Clean Code")."""
    parts = urlsplit(url or "")
    host = parts.netloc.lower().removeprefix("www.").rsplit(".", 1)[0]
    path = _CAMEL.sub(" ", _EXTENSION.sub("", parts.path))
    return f"{host} {path}".replace("_", " ")
