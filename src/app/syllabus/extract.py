"""Parse syllabus pages into the five parts of spec 9.1, with cite-or-refuse (issue #59).

Spec 9.2: deterministic anchors come first, and a document with no week, percentage or
CLO code is refused before any LLM call. The LLM reads the pages as data (spec 12.3)
with the anchors as hints and answers JSON at temperature 0.1, classifying the document
too: lecture slides that mention a week are refused as well. Every value must cite a
page the model was shown: an item without one is dropped, course fields without one are
left empty for the user to fill, and a CLO code or weight its page does not contain is
emptied. The deterministic checks then add the warnings.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.concepts import BLOOM_LEVELS
from app.llm import LLMClient
from app.llm.blocks import BLOCKS
from app.syllabus.anchors import find_anchors, looks_like_syllabus, parse_date
from app.syllabus.checks import SyllabusWarning, check_syllabus
from app.syllabus.parse import integer, text

log = logging.getLogger("app.syllabus")

PROMPT = Path(__file__).parent / "prompts" / "syllabus_v1.txt"
ASSESSMENT_KINDS = ("quiz", "midterm", "final", "project", "other")
DOCUMENT_KINDS = ("syllabus", "lecture_slides", "other")
COURSE_FIELDS = ("code", "title", "credits", "term_start", "term_end", "language")
# A syllabus schedules many weeks or none (spec 9.3); exactly one is a lecture deck about
# its own week, whatever rubric or homework weights it shows, unless CLO codes are written
# in it. One weight alone is a row of an assignment's rubric, not a grading scheme.
LECTURE_WEEKS = 1
MIN_WEIGHTS = 2

_PAGE = {"type": ["integer", "null"]}
_TEXT = {"type": ["string", "null"]}
_NUMBER = {"type": ["number", "null"]}
_TEXTS = {"type": "array", "items": {"type": "string"}}


def _list_of(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object", "properties": properties,
                                       "required": list(properties)}}


SYLLABUS_SCHEMA = {
    "type": "object",
    "properties": {
        "document_kind": {"type": "string", "enum": list(DOCUMENT_KINDS)},
        "course": {"type": "object", "properties": {
            "code": _TEXT, "title": _TEXT, "credits": _NUMBER, "term_start": _TEXT,
            "term_end": _TEXT, "language": _TEXT, "source_page": _PAGE}},
        "outcomes": _list_of({"code": _TEXT, "text": {"type": "string"},
                              "bloom_level": {"type": "string", "enum": list(BLOOM_LEVELS)},
                              "source_page": _PAGE}),
        "weeks": _list_of({"week": {"type": "integer"}, "topics": _TEXTS, "readings": _TEXTS,
                           "source_page": _PAGE}),
        "assessments": _list_of({"title": {"type": "string"},
                                 "kind": {"type": "string", "enum": list(ASSESSMENT_KINDS)},
                                 "weight": _NUMBER, "due_week": {"type": ["integer", "null"]},
                                 "due_date": _TEXT, "source_page": _PAGE}),
        "textbooks": _list_of({"title": {"type": "string"}, "authors": _TEXT,
                               "required": {"type": "boolean"}, "source_page": _PAGE}),
    },
    "required": ["document_kind", "course", "outcomes", "weeks", "assessments", "textbooks"],
}


class NotASyllabus(ValueError):
    """The document has no weekly schedule, assessment or CLO (spec 9.3: ``422``)."""


@dataclass(frozen=True)
class SyllabusDraft:
    """A parsed syllabus waiting for the user to review and confirm it on S4."""

    parsed: dict[str, Any]
    warnings: list[SyllabusWarning] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(w.blocking for w in self.warnings)


def extract_syllabus(llm: LLMClient, pages: list[str]) -> SyllabusDraft:
    """Parse ``pages`` (one string per page, from ``app.ingest.extract_pages``).

    Raises NotASyllabus, ValueError when the answer is not usable JSON, and lets
    RetryableError through when the LLM stays unavailable after its retries.
    """
    anchors = find_anchors(pages)
    if not looks_like_syllabus(anchors):
        raise NotASyllabus("no week, percentage or CLO code in the document")
    document = "\n".join(f"[Page {n}] {page}" for n, page in enumerate(pages, start=1))
    prompt = (BLOCKS.wrap("syllabus_anchors", "\n".join(a.describe() for a in anchors)) + "\n"
              + BLOCKS.wrap("document_text", document))
    answer = llm.complete(prompt, system=PROMPT.read_text(encoding="utf-8"),
                          json_schema=SYLLABUS_SCHEMA, max_tokens=8192,
                          temperature=0.1).text  # thinking counts against max_tokens
    parsed, dropped = parse_answer(answer, pages)
    if not _has_syllabus_evidence(parsed):
        raise NotASyllabus("the model found no schedule, weighted assessment or CLO code")
    warnings = check_syllabus(parsed)
    if dropped:
        warnings.insert(0, SyllabusWarning(
            "missing_source", f"Đã bỏ {dropped} giá trị không tìm thấy trên trang nguồn"))
    return SyllabusDraft(parsed, warnings)


def parse_answer(answer: str, pages: list[str]) -> tuple[dict[str, Any], int]:
    """The cleaned five parts and how many values were dropped: no valid page, no
    content, or a CLO code or weight that is not written on its page.
    Raises ValueError when the answer is not a JSON object, and NotASyllabus when the
    model classifies the document as something else."""
    data = json.loads(answer)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")  # noqa: TRY004
    kind = data.get("document_kind", "syllabus")
    if kind != "syllabus":
        raise NotASyllabus(f"the model classified the document as {kind}")
    numbers = range(1, len(pages) + 1)
    parsed: dict[str, Any] = {"course": _course(data.get("course"), numbers)}
    dropped = int(parsed["course"]["source_page"] is None and _has_course_values(data))
    for part, clean in (("outcomes", _outcome), ("weeks", _week),
                        ("assessments", _assessment), ("textbooks", _textbook)):
        rows = data.get(part) if isinstance(data.get(part), list) else []
        kept = [item for raw in rows if (item := _cited(raw, clean, numbers)) is not None]
        dropped += len(rows) - len(kept)
        parsed[part] = kept
    dropped += _drop_unwritten(parsed, pages)
    if dropped:
        log.info("syllabus: dropped %d uncited, empty or unwritten values", dropped)
    return parsed, dropped


def _drop_unwritten(parsed: dict[str, Any], pages: list[str]) -> int:
    """Empty each CLO code or weight its cited page does not contain: from lecture slides
    the model invents them ("Learning objectives" → CLO1, a deliverable → 100%)."""
    count = 0
    for outcome in parsed["outcomes"]:
        page = re.sub(r"\s+", "", pages[outcome["source_page"] - 1]).casefold()
        if outcome["code"] and outcome["code"].casefold() not in page:
            outcome["code"] = None
            count += 1
    for item in parsed["assessments"]:
        page = pages[item["source_page"] - 1]
        written = {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", page)}
        if item["weight"] is not None and item["weight"] not in written:
            item["weight"] = None
            count += 1
    return count


def _has_syllabus_evidence(parsed: dict[str, Any]) -> bool:
    """A schedule, a grading scheme or CLO codes (issue #59 step 4), each one checked
    against the page text above, so a lecture deck cannot pass on invented values.
    A deck about its own week needs CLO codes: a rubric's weights are not enough."""
    weeks = len(parsed["weeks"])
    has_codes = any(o["code"] for o in parsed["outcomes"])
    if weeks == LECTURE_WEEKS:
        return has_codes
    has_grading = sum(a["weight"] is not None for a in parsed["assessments"]) >= MIN_WEIGHTS
    return weeks > LECTURE_WEEKS or has_grading or has_codes


def _cited(raw: Any, clean, pages: range) -> dict[str, Any] | None:
    """The cleaned item with its ``source_page``, or None when it cites no shown page."""
    if not isinstance(raw, dict) or integer(raw.get("source_page")) not in pages:
        return None
    item = clean(raw)
    return None if item is None else {**item, "source_page": integer(raw["source_page"])}


def _course(raw: Any, pages: range) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    page = integer(raw.get("source_page"))
    if page not in pages:
        return dict.fromkeys((*COURSE_FIELDS, "source_page"))  # left for the user to fill
    return {
        "code": text(raw.get("code")) or None,
        "title": text(raw.get("title")) or None,
        "credits": _number(raw.get("credits")),
        "term_start": _iso_date(raw.get("term_start")),
        "term_end": _iso_date(raw.get("term_end")),
        "language": text(raw.get("language")) or None,
        "source_page": page,
    }


def _has_course_values(data: dict) -> bool:
    course = data.get("course")
    return isinstance(course, dict) and any(course.get(key) for key in COURSE_FIELDS)


def _outcome(raw: dict) -> dict[str, Any] | None:
    description = text(raw.get("text"))
    if not description:
        return None
    bloom = text(raw.get("bloom_level"))
    code = (text(raw.get("code")) or "").replace(" ", "").upper()
    return {"code": code or None, "text": description,
            "bloom_level": bloom if bloom in BLOOM_LEVELS else "understand"}


def _week(raw: dict) -> dict[str, Any] | None:
    week, topics = integer(raw.get("week")), _texts(raw.get("topics"))
    if week is None or week < 1 or not topics:
        return None
    return {"week": week, "topics": topics, "readings": _texts(raw.get("readings"))}


def _assessment(raw: dict) -> dict[str, Any] | None:
    title = text(raw.get("title"))
    if not title:
        return None
    kind = text(raw.get("kind"))
    weight, due_week = _number(raw.get("weight")), integer(raw.get("due_week"))
    return {
        "title": title,
        "kind": kind if kind in ASSESSMENT_KINDS else "other",
        "weight": weight if weight is not None and 0 <= weight <= 100 else None,
        "due_week": due_week if due_week is not None and due_week >= 1 else None,
        "due_date": _iso_date(raw.get("due_date")),
    }


def _textbook(raw: dict) -> dict[str, Any] | None:
    title = text(raw.get("title"))
    if not title:
        return None
    return {"title": title, "authors": text(raw.get("authors")) or None,
            "required": raw.get("required") is True}


def _iso_date(value: Any) -> str | None:
    found = parse_date(value)
    return found.isoformat() if found else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for item in value if isinstance(item, str) and (t := item.strip())]
