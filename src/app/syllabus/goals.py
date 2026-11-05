"""A self-learner without a syllabus pastes their goals or a table of contents (spec 9.3).

The paste becomes a draft syllabus in the shape the parser already reads, "Week N:
goal; goal", one goal per line spread evenly over at most 12 weeks. From there it
takes the same path as an uploaded syllabus: preview, the learner edits and
confirms, the roadmap is derived, material is mapped onto it (#114 step 6). Every
topic is the learner's own line, so nothing in the draft is invented.
"""

from __future__ import annotations

import re

from app.syllabus.extract import NotASyllabus

MAX_WEEKS = 12
HEADER = "Syllabus (draft from your learning goals)"
# Bullets, numbering, and a week label the learner already wrote.
_PREFIX = re.compile(
    r"^\s*(?:[-*•▪◦+]\s*|\(?\d{1,3}[.)]\s*|[a-z][.)]\s+|(?:week|tuần)\s*\d{1,2}\s*[:.\-–]\s*)+",
    re.IGNORECASE,
)


def goals(text: str) -> list[str]:
    """The learner's goals, one per non-trivial line, without bullets or duplicates."""
    found = {}
    for line in text.splitlines():
        if line.rstrip().endswith(":"):
            continue  # a heading such as "Goals:" introduces goals, it is not one
        goal = _PREFIX.sub("", line).strip(" \t.;:")
        if len(goal) >= 3:
            found.setdefault(goal.casefold(), goal)
    return list(found.values())


def goals_syllabus(text: str) -> str:
    """The draft syllabus text for pasted goals; NotASyllabus when there are none."""
    items = goals(text)
    if not items:
        raise NotASyllabus("Không thấy mục tiêu nào; mỗi dòng nên là một mục tiêu học.")
    weeks = min(MAX_WEEKS, len(items))
    size, extra = divmod(len(items), weeks)
    lines, start = [HEADER], 0
    for week in range(1, weeks + 1):
        end = start + size + (week <= extra)  # earlier weeks take the remainder
        lines.append(f"Week {week}: " + "; ".join(items[start:end]))
        start = end
    return "\n".join(lines)
