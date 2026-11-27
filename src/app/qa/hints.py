"""Hint ladder for a quoted exercise (issue #163, UC-13, spec 12.5).

1. the node's concept and its most relevant source; 2. the exercise's own source
page and the learner's last answer; 3. the source's own answer or solution.
Every hint is assembled from stored fields and no model writes one, so nothing a
learner types can talk the ladder into an answer: the gates below are the whole
anti-leak policy. Levels 1-2 end with a question that hands the turn back.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Issue #163: no solution before the learner has tried. Spec 12.5 asks for three
# tries, but the attempt endpoint (#115) already shows the source's key after one.
ATTEMPTS_BEFORE_SOLUTION = 1


@dataclass(frozen=True)
class Hint:
    level: int
    content: str
    refused: bool = False
    reason: str | None = None


def _where(citation: dict[str, Any], location: str | None) -> str:
    parts = [citation.get("title") or "the exercise source"]
    if citation.get("page"):
        parts.append(f"page {citation['page']}")
    if location:
        parts.append(location.rstrip(":"))
    return ", ".join(parts)


def exercise_hint(
    exercise: Any,
    citation: dict[str, Any],
    *,
    level: int,
    graded: bool,
    attempts: Sequence[Any],
    concept: str,
    reading: str | None = None,
) -> Hint:
    """Hint ``level`` (1-3) for ``exercise``; ``attempts`` are the learner's, oldest first.

    A graded item never reaches level 3; a practice item reaches it only after
    :data:`ATTEMPTS_BEFORE_SOLUTION` attempts. ``reading`` names the node's most
    relevant source for level 1.
    """
    if level >= 3 and graded:
        return Hint(
            1,
            "This is a graded exercise, so only levels 1-2 hints are available — no solutions. "
            f"Try reviewing the concept '{concept}' and continue from there?",
            refused=True,
            reason="graded",
        )
    if level >= 3 and len(attempts) < ATTEMPTS_BEFORE_SOLUTION:
        return Hint(
            1,
            "The source solution unlocks only after you attempt an answer first. "
            "What do you think the first step to solve this problem is?",
            refused=True,
            reason="attempt_first",
        )
    where = _where(citation, exercise.location)
    if level == 1:
        see = f" Most relevant source for this stage: {reading}." if reading else ""
        return Hint(
            1,
            f"Hint level 1: this exercise uses the concept '{concept}'.{see} "
            "Which detail in the prompt relates most closely to that concept?",
        )
    if level == 2:
        last = attempts[-1].response if attempts else None
        tried = (
            f" Last time you answered '{last}': check the first assumption you used."
            if last
            else ""
        )
        return Hint(
            2,
            f"Hint level 2: check {where}.{tried} "
            "Which rule or definition there applies to this prompt?",
        )
    shown = [f"Source answer: {exercise.answer}"] if exercise.answer else []
    if exercise.solution_ref:
        shown.append(f"Source solution: {exercise.solution_ref}")
    if not shown:
        return Hint(3, f"The source does not include a solution; check your work against {where}.")
    return Hint(3, f"{'. '.join(shown)} ({where}).")
