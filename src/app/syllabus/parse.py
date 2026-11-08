"""Normalize a syllabus request (spec 8.1) into raw text, outcomes and assessments.

The API accepts the schema's column names and the spec's aliases (text/outcomes/title/
due "week 8"/parsed{...}); this module reduces them to one shape. No web or ORM types.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_WEEK = re.compile(r"(?:week|tuần)\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Outcome:
    code: str
    description: str
    bloom_level: str = "understand"


@dataclass(frozen=True)
class AssessmentItem:
    name: str
    weight: float = 0.0
    due_week: int | None = None


@dataclass(frozen=True)
class SyllabusParts:
    """What a request sets; None means the request leaves that part as stored (PUT is partial)."""

    raw_text: str | None
    outcomes: list[Outcome] | None
    assessments: list[AssessmentItem] | None


def parse_syllabus(payload: dict[str, Any], fields: set[str]) -> SyllabusParts:
    """``payload`` is the request body as a dict, ``fields`` the keys the client actually sent.

    An explicit empty list clears outcomes or assessments; an omitted one keeps them.
    """
    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}

    raw: str | None = None
    if "raw_text" in fields:
        raw = text(payload.get("raw_text")) or ""
    elif "text" in fields:
        raw = text(payload.get("text")) or ""
    elif "parsed" in fields:
        raw = text(parsed.get("raw_text")) or text(parsed.get("text"))
        if raw is None:
            raw = json.dumps(parsed, ensure_ascii=False) if parsed else ""

    outcome_rows = _first_list(payload, fields, parsed, ("learning_outcomes", "outcomes"))
    assessment_rows = _first_list(payload, fields, parsed, ("assessments",))
    return SyllabusParts(
        raw_text=raw,
        outcomes=None if outcome_rows is None else _outcomes(outcome_rows),
        assessments=None if assessment_rows is None else _assessments(assessment_rows),
    )


def text(value: Any) -> str | None:
    if value is None:
        return None
    return value.strip() if isinstance(value, str) else str(value).strip()


def integer(value: Any) -> int | None:
    """An int from 3, 3.0 or "3 tuần"; None when there is no number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def _number(value: Any) -> float:
    """A float from 30, "30%" or "12,5"; 0 when there is no number."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    return float(match.group().replace(",", ".")) if match else 0.0


def _due_week(row: dict[str, Any]) -> int | None:
    value = integer(row.get("due_week"))
    if value is not None:
        return value
    for key in ("due", "week"):
        raw = text(row.get(key))
        if not raw:
            continue
        match = _WEEK.search(raw)
        if match:
            return int(match.group(1))
        if raw.isdigit():
            return int(raw)
    return None


def _first_list(payload, fields, parsed, keys) -> list | None:
    for key in keys:
        if key in fields:
            return payload.get(key) or []
    for key in keys:
        if "parsed" in fields and key in parsed:
            return parsed.get(key) or []
    return None


def _rows(items: list, key: str) -> list[tuple[int, dict]]:
    """Plain strings become ``{key: item}``; anything that is not a dict is skipped."""
    rows = []
    for index, item in enumerate(items, start=1):
        row = {key: item} if isinstance(item, str) else item
        if isinstance(row, dict):
            rows.append((index, row))
    return rows


def _outcomes(items: list) -> list[Outcome]:
    outcomes = []
    for index, row in _rows(items, "description"):
        code = text(row.get("code"))
        description = text(row.get("description") or row.get("text") or row.get("title"))
        if code or description:
            outcomes.append(Outcome(
                code=code or f"CLO{index}",
                description=description or code,
                bloom_level=text(row.get("bloom_level")) or "understand",
            ))
    return outcomes


def _assessments(items: list) -> list[AssessmentItem]:
    return [
        AssessmentItem(
            name=text(row.get("name") or row.get("title")) or f"Assessment {index}",
            weight=_number(row.get("weight")),
            due_week=_due_week(row),
        )
        for index, row in _rows(items, "name")
    ]
