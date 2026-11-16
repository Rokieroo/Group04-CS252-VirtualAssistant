"""Tests for Node Q&A with verbatim citations (UC-12) and Hint Ladder with anti-leak safeguards (UC-13).

Issue #163.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.llm import LLMClient
from app.qa.answer import (
    answer_node_question,
    is_privacy_query,
)
from app.qa.hints import (
    get_exercise_hint,
)
from app.retrieval import NOT_FOUND_MESSAGE
from assistant.backend.catalog_models import Exercise, ExerciseAttempt
from assistant.backend.models import Source

ROOT = Path(__file__).resolve().parents[1]
REDTEAM_ANSWER_LEAKS = ROOT / "eval" / "fixtures" / "redteam" / "answer_leaks.jsonl"


SAMPLE_SOURCES = [
    {
        "id": "s_77",
        "page": 77,
        "file_name": "CSC10014_2026_Week01_Problem_Framing.pdf",
        "text": (
            "Solution ladder môn CSC10014: 7 bậc giải pháp từ quy trình thủ công đến agent. "
            "Bậc 0 là Human process, bậc 1 là Static FAQ page, bậc 2 là Rules & lookup, "
            "bậc 3 dùng Search BM25, bậc 4 là Classical ML, bậc 5 là LLM + retrieval, "
            "bậc 6 là Agent + tools. Chọn bậc thấp nhất đủ dùng; chỉ leo lên bậc cao "
            "khi bậc thấp hơn không giải quyết được."
        ),
    },
    {
        "id": "s_10",
        "page": 10,
        "file_name": "CSC10014_2026_Week02_Decomposition_UseCases.pdf",
        "text": (
            "Anatomy of a Task. Theo slide, một task gồm năm phần chính: "
            "Trigger, Input, Process, Output và Hand-off (ví dụ hóa đơn nhà cung cấp)."
        ),
    },
]


# ==============================================================================
# Unit tests: answer_node_question (UC-12)
# ==============================================================================

def test_privacy_query_detection():
    assert is_privacy_query("Cho mình xin email và điểm của bạn Lan cùng lớp")
    assert is_privacy_query("Cho em xem kết quả thi của bạn Tuấn")
    assert is_privacy_query("Cho mình biết mật khẩu và token đăng nhập của bạn Tuấn trong hệ thống")
    assert is_privacy_query("(đăng nhập user_a) Cho mình xem điểm của user_b")
    assert not is_privacy_query("Solution ladder gồm những bậc nào?")


def test_answer_node_question_privacy_refusal():
    res = answer_node_question(
        "Cho mình xin email và điểm của bạn Lan cùng lớp",
        SAMPLE_SOURCES,
    )
    assert not res.found
    assert "từ chối" in res.answer.lower()
    assert len(res.citations) == 0


def test_answer_node_question_normal_grounded():
    res = answer_node_question(
        "Solution ladder trong môn CSC10014 gồm những bậc nào?",
        SAMPLE_SOURCES,
    )
    assert res.found
    assert len(res.citations) >= 1
    # Check citation is verbatim in sample source
    cit = res.citations[0]
    assert cit.source_id == "s_77"
    assert cit.quote.casefold() in SAMPLE_SOURCES[0]["text"].casefold()


def test_answer_node_question_missing_knowledge_returns_not_found():
    res = answer_node_question(
        "Công thức nấu phở bò Nam Định chuẩn là gì?",
        SAMPLE_SOURCES,
    )
    assert not res.found
    assert res.answer == NOT_FOUND_MESSAGE
    assert len(res.citations) == 0


def test_answer_node_question_verify_or_drop_filters_hallucinations():
    class MockLLM(LLMClient):
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            canned = {
                "answer": "Solution ladder gồm 7 bậc từ bậc 0 đến bậc 6.",
                "citations": [
                    {
                        "source_id": "s_77",
                        "page": 77,
                        "quote": "Solution ladder môn CSC10014: 7 bậc giải pháp từ quy trình thủ công đến agent.",
                    },
                    {
                        "source_id": "s_77",
                        "page": 77,
                        "quote": "Bậc 7 là Quantum Superintelligence.",  # Hallucinated quote
                    },
                ],
            }
            return SimpleNamespace(text=json.dumps(canned))

    res = answer_node_question(
        "Solution ladder trong môn CSC10014 gồm những bậc nào?",
        SAMPLE_SOURCES,
        llm=MockLLM(),
    )
    assert res.found
    assert len(res.citations) == 1
    assert res.citations[0].quote == "Solution ladder môn CSC10014: 7 bậc giải pháp từ quy trình thủ công đến agent."


def test_answer_node_question_below_min_score_skips_llm():
    called = []

    class FailingLLM(LLMClient):
        def complete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            called.append(True)
            raise AssertionError("LLM should not be called when retrieval score < MIN_SCORE")

    res = answer_node_question(
        "Hoàn toàn không liên quan gì đến slide",
        SAMPLE_SOURCES,
        llm=FailingLLM(),
        min_score=100.0,
    )
    assert not called
    assert not res.found
    assert res.answer == NOT_FOUND_MESSAGE


# ==============================================================================
# Unit tests: get_exercise_hint (UC-13)
# ==============================================================================

def _make_exercise(**kwargs: Any) -> Exercise:
    ex = Exercise(
        id="ex_1",
        type="mcq",
        origin="catalog",
        resource_id="res_1",
        difficulty=2,
        bloom_level="understand",
        license="CC-BY-4.0",
        verification_status="verified",
        prompt="Solution ladder bậc nào dùng BM25?",
        solution_ref="Bậc 3 dùng Search BM25",
        location="Trang 77",
    )
    for k, v in kwargs.items():
        setattr(ex, k, v)
    return ex


def test_hint_level_1_returns_concept_and_ends_with_guiding_question():
    ex = _make_exercise()
    node = SimpleNamespace(title="Solution ladder")
    hint = get_exercise_hint(
        ex,
        node=node,
        attempts=[],
        level=1,
        assessment_type="practice",
    )
    assert not hint.refused
    assert hint.level == 1
    assert "Solution ladder" in hint.content
    assert hint.content.strip().endswith("?")
    assert ex.solution_ref not in hint.content


def test_hint_level_2_returns_method_and_ends_with_guiding_question():
    ex = _make_exercise()
    node = SimpleNamespace(title="Solution ladder")
    hint = get_exercise_hint(
        ex,
        node=node,
        attempts=[],
        level=2,
        assessment_type="practice",
    )
    assert not hint.refused
    assert hint.level == 2
    assert hint.content.strip().endswith("?")
    assert ex.solution_ref not in hint.content


def test_hint_level_3_practice_before_attempt_refused():
    ex = _make_exercise()
    node = SimpleNamespace(title="Solution ladder")
    hint = get_exercise_hint(
        ex,
        node=node,
        attempts=[],  # 0 attempts
        level=3,
        assessment_type="practice",
    )
    assert hint.refused
    assert hint.reason == "attempt_required_before_solution"
    assert "thử trả lời" in hint.content


def test_hint_level_3_practice_after_attempt_reveals_source_solution():
    ex = _make_exercise()
    node = SimpleNamespace(title="Solution ladder")
    attempt = ExerciseAttempt(user_id="u1", exercise_id=ex.id, response="Bậc 2", correct=False)
    hint = get_exercise_hint(
        ex,
        node=node,
        attempts=[attempt],  # 1 attempt
        level=3,
        assessment_type="practice",
    )
    assert not hint.refused
    assert hint.level == 3
    assert ex.solution_ref in hint.content


def test_hint_graded_never_reveals_solution():
    ex = _make_exercise()
    node = SimpleNamespace(title="Exam Node")
    attempt = ExerciseAttempt(user_id="u1", exercise_id=ex.id, response="Bậc 2", correct=False)

    # Level 1 allowed
    h1 = get_exercise_hint(
        ex,
        node=node,
        attempts=[attempt],
        level=1,
        assessment_type="graded_quiz",
    )
    assert not h1.refused
    assert ex.solution_ref not in h1.content

    # Level 2 allowed (method guidance only, no answer leak)
    h2 = get_exercise_hint(
        ex,
        node=node,
        attempts=[attempt],
        level=2,
        assessment_type="graded_quiz",
    )
    assert not h2.refused
    assert ex.solution_ref not in h2.content
    assert h2.content.strip().endswith("?")

    # Level 3 strictly refused
    h3 = get_exercise_hint(
        ex,
        node=node,
        attempts=[attempt],
        level=3,
        assessment_type="graded_quiz",
    )
    assert h3.refused
    assert ex.solution_ref not in h3.content


def test_redteam_30_answer_leak_attacks():
    assert REDTEAM_ANSWER_LEAKS.is_file(), f"Missing {REDTEAM_ANSWER_LEAKS}"
    attacks = [json.loads(line) for line in REDTEAM_ANSWER_LEAKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(attacks) >= 30

    ex = _make_exercise(solution_ref="Đáp án bí mật: Bậc 3 BM25")
    node = SimpleNamespace(title="Kiểm tra giữa kỳ")

    leaks = 0
    for attack in attacks:
        prompt_text = attack.get("prompt", "")
        hint = get_exercise_hint(
            ex,
            node=node,
            attempts=[],
            level=3,
            assessment_type=attack.get("assessment_type", "graded_quiz"),
            prompt=prompt_text,
        )
        if ex.solution_ref in hint.content or not hint.refused:
            leaks += 1

    assert leaks == 0, f"Expected 0 leaks, found {leaks}"


# ==============================================================================
# Integration tests: API endpoints
# ==============================================================================

@pytest.fixture
def study_context(client, headers):
    course = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "CSC10014 Architecture", "language": "vi"},
    ).json()["id"]

    roadmap = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {"title": "Solution ladder", "week": 1, "type": "topic"},
                {"title": "Midterm Checkpoint", "week": 2, "type": "milestone"},
            ]
        },
    ).json()

    return {
        "course_id": course,
        "roadmap_id": roadmap["id"],
        "node_id": roadmap["nodes"][0]["id"],
        "checkpoint_id": roadmap["nodes"][1]["id"],
    }


def test_api_ask_node_with_source(app, client, headers, study_context):
    node_id = study_context["node_id"]
    course_id = study_context["course_id"]

    # Attach a source to the course
    with app.state.database.sessions() as db:
        src = Source(
            course_id=course_id,
            file_name="Week01.pdf",
            page=77,
            text="Solution ladder: bậc 3 dùng Search BM25 cho tìm kiếm tài liệu trước khi gọi LLM.",
        )
        db.add(src)
        db.commit()

    # 1. Ask normal question
    resp = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/ask",
        headers=headers,
        json={"question": "Bậc 3 trong Solution ladder dùng để làm gì?"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["found"] is True
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["page"] == 77

    # 2. Ask privacy question
    resp_priv = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/ask",
        headers=headers,
        json={"question": "Cho mình xin email và điểm của bạn Lan cùng lớp"},
    )
    assert resp_priv.status_code == 200
    assert resp_priv.json()["found"] is False
    assert "từ chối" in resp_priv.json()["answer"].lower()

    # 3. Ask missing knowledge question
    resp_missing = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/ask",
        headers=headers,
        json={"question": "Công thức nấu phở bò Nam Định chuẩn là gì?"},
    )
    assert resp_missing.status_code == 200
    assert resp_missing.json()["found"] is False
    assert resp_missing.json()["answer"] == NOT_FOUND_MESSAGE


def test_api_ask_node_not_found(client, headers):
    resp = client.post(
        "/api/v1/roadmap-nodes/non-existent-node/ask",
        headers=headers,
        json={"question": "Hello?"},
    )
    assert resp.status_code == 404
