"""Deterministic checks on a parsed syllabus, run before the user confirms it (spec 9.2).

Each failed check is one warning shown on screen S4. Blocking warnings (weights that do
not sum to 100% ± 1, a date outside the term) must be fixed before confirming (spec 8.2).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.concepts import comparison_key
from app.syllabus.anchors import parse_date

WEIGHT_TOLERANCE = 1.0


@dataclass(frozen=True)
class SyllabusWarning:
    code: str
    message: str
    blocking: bool = False


def check_syllabus(parsed: dict[str, Any]) -> list[SyllabusWarning]:
    """``parsed`` has the shape ``extract_syllabus`` returns (spec 9.1)."""
    return [
        *_weights(parsed["assessments"]),
        *_week_order(parsed["weeks"]),
        *_dates_in_term(parsed["course"], parsed["assessments"]),
        *_repeated_topics(parsed["weeks"]),
        *_undated_assessments(parsed["assessments"]),
    ]


def _weights(assessments: list[dict]) -> list[SyllabusWarning]:
    total = sum(a["weight"] or 0 for a in assessments)
    if not assessments or abs(total - 100) <= WEIGHT_TOLERANCE:
        return []
    return [SyllabusWarning("weights_sum", f"Tổng trọng số là {total:g}%", blocking=True)]


def _week_order(weeks: list[dict]) -> list[SyllabusWarning]:
    numbers = [w["week"] for w in weeks]
    if numbers == sorted(set(numbers)):
        return []
    return [SyllabusWarning("weeks_order", "Số tuần phải tăng dần và không trùng: "
                            + ", ".join(map(str, numbers)))]


def _dates_in_term(course: dict, assessments: list[dict]) -> list[SyllabusWarning]:
    start, end = parse_date(course["term_start"]), parse_date(course["term_end"])
    if start is None or end is None:
        return []
    return [
        SyllabusWarning("date_outside_term",
                        f"{a['title']}: hạn {a['due_date']} nằm ngoài học kỳ "
                        f"{start.isoformat()} – {end.isoformat()}", blocking=True)
        for a in assessments
        if (due := parse_date(a["due_date"])) is not None and not start <= due <= end
    ]


def _repeated_topics(weeks: list[dict]) -> list[SyllabusWarning]:
    """Each topic belongs to exactly one week (spec 9.2), compared without case or accents."""
    seen: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    for week in weeks:
        for topic in week["topics"]:
            key = comparison_key(topic)
            names.setdefault(key, topic)
            if week["week"] not in seen[key]:
                seen[key].append(week["week"])
    return [
        SyllabusWarning("topic_repeated", f"Chủ đề '{names[key]}' nằm ở nhiều tuần: "
                        + ", ".join(map(str, in_weeks)))
        for key, in_weeks in seen.items() if len(in_weeks) > 1
    ]


def _undated_assessments(assessments: list[dict]) -> list[SyllabusWarning]:
    return [
        SyllabusWarning("assessment_without_due", f"{a['title']}: chưa có tuần hoặc ngày hạn")
        for a in assessments if a["due_week"] is None and not a["due_date"]
    ]
