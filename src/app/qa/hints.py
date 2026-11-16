"""Step-by-step hint ladder and anti-leak safeguards (issue #163, UC-13).

Provides 3-level hint progression without ever authoring answers:
Level 1: Related concept + source link/location + guiding question.
Level 2: Guiding premise/method + source page + guiding question.
Level 3: Exact quoted source answer (practice only, after at least 1 attempt).

Strictly refuses solutions for graded items and pre-attempt queries (0 leaks).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

GRADED_ASSESSMENTS = frozenset(
    {"graded_quiz", "midterm_exam", "final_exam", "graded_assignment"}
)

_LEAK_PATTERNS = [
    re.compile(r"\b(?:xin|cho|in|xuất|output|give|print|show)\b.*\b(?:đáp án|answer|key|solution|rubric|lời giải)\b", re.IGNORECASE),
    re.compile(r"\b(?:master answer key|admin|override|sudo|debug mode)\b", re.IGNORECASE),
    re.compile(r"\b(?:giảng viên|giáo viên|professor|trợ giảng|ta)\b.*\b(?:đáp án|solution|answer key)\b", re.IGNORECASE),
    re.compile(r"\b(?:bỏ qua mọi|ignore previous|system prompt)\b", re.IGNORECASE),
    re.compile(r"\b(?:hết giờ|khẩn cấp|điểm 0)\b.*\b(?:đáp án|câu trả lời|lời giải)\b", re.IGNORECASE),
    re.compile(r"\b(?:đáp án câu|answer to question|correct answer letter)\b", re.IGNORECASE),
]


@dataclass
class HintResult:
    level: int
    content: str
    source_id: str | None = None
    page: int | None = None
    refused: bool = False
    reason: str = ""


def is_leak_attempt(prompt: str) -> bool:
    """Return True if ``prompt`` attempts to extract the final answer or solution."""
    if not prompt:
        return False
    text = prompt.strip()
    return any(p.search(text) for p in _LEAK_PATTERNS)


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_exercise_hint(
    exercise: Any,
    node: Any | None = None,
    attempts: Sequence[Any] = (),
    level: int = 1,
    assessment_type: str = "practice",
    prompt: str | None = None,
    node_sources: Sequence[Any] = (),
) -> HintResult:
    """Produce a stepped hint or refusal adhering to anti-leak constraints (UC-13).

    - Graded items: final answer is NEVER given under any circumstances (max level 1).
    - Practice items: answer requires at least 1 prior attempt before level 3.
    - All hints (except level 3) end with a guiding question giving the turn back.
    """
    is_graded = (
        assessment_type in GRADED_ASSESSMENTS
        or _field(node, "type") == "milestone"
        or (prompt and ("graded" in prompt.lower() or "tính điểm" in prompt.lower()))
    )
    attempt_count = len(attempts)

    # 1. Anti-leak checks
    if is_graded and (level >= 3 or is_leak_attempt(prompt or "")):
        return HintResult(
            level=1,
            content=(
                "Đây là bài kiểm tra tính điểm. Hệ thống chỉ cung cấp gợi ý định hướng "
                "(bậc 1), không cung cấp đáp án hoặc lời giải chi tiết. "
                "Bạn hãy xem lại khái niệm liên quan để tự hoàn thành nhé?"
            ),
            refused=True,
            reason="graded_assessment_anti_leak",
        )

    if not is_graded and attempt_count == 0 and (level >= 3 or is_leak_attempt(prompt or "")):
        return HintResult(
            level=1,
            content=(
                "Bạn cần thử trả lời bài tập ít nhất một lần trước khi xem lời giải của nguồn. "
                "Bạn nghĩ bước đầu tiên để tiếp cận câu hỏi này là gì?"
            ),
            refused=True,
            reason="attempt_required_before_solution",
        )

    # 2. Extract exercise context
    ex_answer = (
        _field(exercise, "solution_ref")
        or _field(exercise, "answer")
        or _field(exercise, "solution")
    )
    source_id = _field(exercise, "source_id") or _field(exercise, "resource_id")
    page = _field(exercise, "page")
    node_title = str(_field(node, "title") or "").strip()

    # Find matching source citation
    source_title = ""
    for s in node_sources:
        sid = _field(s, "id") or _field(s, "source_id")
        if sid == source_id:
            source_title = str(_field(s, "file_name") or _field(s, "title") or "")
            if page is None:
                page = _field(s, "page")
            break

    # 3. Hint Ladder Levels
    if level == 1:
        # Bậc 1: Gợi ý khái niệm liên quan + link/tên nguồn + câu hỏi gợi mở
        concept = node_title or "khái niệm trọng tâm của bài toán"
        loc = f"trang {page}" if page else (source_title or "tài liệu của chặng")
        content = (
            f"Gợi ý bậc 1: Bài tập này kiểm tra kiến thức về '{concept}'. "
            f"Bạn có thể xem lại tại {loc}. "
            f"Theo bạn, dữ kiện quan trọng nhất được đề bài nhắc đến là gì?"
        )
        return HintResult(level=1, content=content, source_id=source_id, page=page)

    if level == 2:
        # Bậc 2: Định hướng phương pháp / trang nguồn + câu hỏi gợi mở
        loc = f"trang {page}" if page else (source_title or "tài liệu của chặng")
        last_attempt = attempts[-1] if attempts else None
        last_resp = _field(last_attempt, "response") if last_attempt else None
        feedback = f" Ở lần thử trước bạn đã chọn '{last_resp}', hãy chú ý tiền đề cốt lõi." if last_resp else ""
        content = (
            f"Gợi ý bậc 2: Hãy đối chiếu phương pháp xử lý tại {loc}.{feedback} "
            f"Bạn hãy thử xác định công thức hoặc quy tắc tương ứng trước khi tính toán nhé?"
        )
        return HintResult(level=2, content=content, source_id=source_id, page=page)

    # Level 3: Lời giải của nguồn (không tự viết lời giải)
    if ex_answer is not None and str(ex_answer).strip():
        ans_str = str(ex_answer).strip()
        content = f"Lời giải từ nguồn ({source_title or 'tài liệu'}): {ans_str}"
    else:
        loc = f"trang {page}" if page else (source_title or "tài liệu")
        content = f"Lời giải tự đối chiếu: Vui lòng đối chiếu bài làm trực tiếp với {loc}."

    return HintResult(level=3, content=content, source_id=source_id, page=page)
