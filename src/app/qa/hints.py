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
    parts = [citation.get("title") or "nguồn của bài"]
    if citation.get("page"):
        parts.append(f"trang {citation['page']}")
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
            "Đây là bài tính điểm nên chỉ có gợi ý bậc 1-2, không có lời giải. "
            f"Bạn thử xem lại khái niệm '{concept}' rồi làm tiếp nhé?",
            refused=True,
            reason="graded",
        )
    if level >= 3 and len(attempts) < ATTEMPTS_BEFORE_SOLUTION:
        return Hint(
            1,
            "Lời giải của nguồn chỉ mở sau khi bạn đã thử trả lời. "
            "Theo bạn, bước đầu tiên để giải bài này là gì?",
            refused=True,
            reason="attempt_first",
        )
    where = _where(citation, exercise.location)
    if level == 1:
        see = f" Nguồn liên quan nhất của chặng: {reading}." if reading else ""
        return Hint(
            1,
            f"Gợi ý bậc 1: bài này dùng khái niệm '{concept}'.{see} "
            "Dữ kiện nào trong đề liên quan nhất tới khái niệm đó?",
        )
    if level == 2:
        last = attempts[-1].response if attempts else None
        tried = (
            f" Lần trước bạn trả lời '{last}': hãy kiểm tra tiền đề đầu tiên bạn dùng."
            if last
            else ""
        )
        return Hint(
            2,
            f"Gợi ý bậc 2: đối chiếu với {where}.{tried} "
            "Quy tắc nào ở đó áp dụng được cho đề này?",
        )
    shown = [f"Đáp án của nguồn: {exercise.answer}"] if exercise.answer else []
    if exercise.solution_ref:
        shown.append(f"Lời giải của nguồn: {exercise.solution_ref}")
    if not shown:
        return Hint(3, f"Nguồn không in lời giải; hãy tự đối chiếu bài làm với {where}.")
    return Hint(3, f"{'. '.join(shown)} ({where}).")
