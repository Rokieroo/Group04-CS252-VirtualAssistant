"""Deterministic syllabus anchors: dates, "Tuần N"/"Week N", percentages, CLO codes (spec 9.2).

They are found before any LLM call: the prompt gets them as hints, and a document with no
week, percentage or CLO code at all is refused as ``not_a_syllabus`` for free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Day first, as Vietnamese syllabi write it (07/09/2026, 7-9-2026, 07.09.2026), or ISO.
_DMY = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_WEEK = re.compile(r"\b(?:week|tuần)\s*(\d{1,2})\b", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")
_CLO = re.compile(r"\bCLO\s*(\d{1,2})\b", re.IGNORECASE)


@dataclass(frozen=True)
class PageAnchors:
    """What one page (numbered from 1) holds, in reading order without repeats."""

    page: int
    dates: tuple[date, ...] = ()
    weeks: tuple[int, ...] = ()
    percents: tuple[float, ...] = ()
    clos: tuple[str, ...] = ()

    def describe(self) -> str:
        """One prompt line, e.g. ``[Page 3] weeks 1, 2 | 30%, 70% | CLO1 | 2026-09-07``."""
        parts = [
            "weeks " + ", ".join(map(str, self.weeks)) if self.weeks else "",
            ", ".join(f"{p:g}%" for p in self.percents),
            ", ".join(self.clos),
            ", ".join(d.isoformat() for d in self.dates),
        ]
        return f"[Page {self.page}] " + " | ".join(part for part in parts if part)


def find_anchors(pages: list[str]) -> list[PageAnchors]:
    """Anchors of every page that has any; pages without one are left out."""
    found = []
    for number, page in enumerate(pages, start=1):
        anchors = PageAnchors(
            page=number,
            dates=_unique(_dates(page)),
            weeks=_unique(int(m) for m in _WEEK.findall(page) if int(m) >= 1),
            percents=_unique(float(m.replace(",", ".")) for m in _PERCENT.findall(page)),
            clos=_unique(f"CLO{int(m)}" for m in _CLO.findall(page)),
        )
        if anchors.dates or anchors.weeks or anchors.percents or anchors.clos:
            found.append(anchors)
    return found


def looks_like_syllabus(anchors: list[PageAnchors]) -> bool:
    """A syllabus names weeks, assessment weights or CLOs; dates alone (a slide's title
    page) do not count (issue #59 step 4)."""
    return any(a.weeks or a.percents or a.clos for a in anchors)


def parse_date(value: object) -> date | None:
    """A date from ISO ``2026-09-07`` or day-first ``07/09/2026``; None when there is none."""
    found = _dates(str(value or ""))
    return found[0] if found else None


def _dates(page: str) -> list[date]:
    matches = [(m.start(), (m[1], m[2], m[3])) for m in _ISO.finditer(page)]
    matches += [(m.start(), (m[3], m[2], m[1])) for m in _DMY.finditer(page)]
    dates = []
    for _, (year, month, day) in sorted(matches):
        try:
            dates.append(date(int(year), int(month), int(day)))
        except ValueError:  # 31/02/2026 or a version number such as 1.2.2026
            continue
    return dates


def _unique(values) -> tuple:
    return tuple(dict.fromkeys(values))
