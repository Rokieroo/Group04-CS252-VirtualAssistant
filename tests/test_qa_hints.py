"""Issue #163 done-when: node answers are quoted or refused; hints never leak a solution."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from conftest import register
from test_exercise_bank import PROBLEMS, _attach

from app.llm import LLMClient
from app.llm.base import LLMResult
from app.qa import answer_question, exercise_hint
from app.retrieval import NOT_FOUND_MESSAGE
from assistant.backend.models import Source

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import run_qa

PAGES = [
    {
        "id": "s_77",
        "page": 77,
        "file_name": "week01.pdf",
        "text": (
            "Solution ladder: 7 bậc từ quy trình thủ công đến agent. "
            "Bậc 3 dùng Search BM25 để tìm tài liệu trước khi gọi LLM. "
            "Chọn bậc thấp nhất đủ dùng."
        ),
    },
    {
        "id": "s_10",
        "page": 10,
        "file_name": "week02.pdf",
        "text": "Anatomy of a task: Trigger, Input, Process, Output và Hand-off.",
    },
    {
        "id": "s_49",
        "page": 49,
        "file_name": "week02.pdf",
        "text": "Dùng include khi luôn xảy ra; dùng extend khi có điều kiện.",
    },
]
QUESTION = "Bậc 3 dùng gì để tìm tài liệu?"


class Scripted(LLMClient):
    """Replies with ``reply`` and counts calls; ``fail`` raises like a quota error."""

    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.calls = reply, fail, 0

    def complete(self, prompt, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("quota exhausted")
        return LLMResult(text=json.dumps(self.reply), input_tokens=0, output_tokens=0, cost_usd=0.0)


def test_offline_answer_quotes_the_best_sentence_of_the_top_page():
    answer = answer_question(QUESTION, PAGES, llm=Scripted({}))
    assert answer.found
    assert answer.text == "Bậc 3 dùng Search BM25 để tìm tài liệu trước khi gọi LLM."
    [citation] = answer.citations
    assert (citation.source_id, citation.page, citation.quote) == ("s_77", 77, answer.text)


def test_too_little_evidence_says_not_found_without_calling_the_model():
    llm = Scripted({"answer": "bịa", "citations": []})
    answer = answer_question("Định lý Bayes phát biểu thế nào?", PAGES, llm=llm)
    assert answer.text == NOT_FOUND_MESSAGE and not answer.found and llm.calls == 0


def test_a_quote_not_on_a_retrieved_page_is_dropped_and_pages_come_from_retrieval():
    llm = Scripted(
        {
            "answer": "Bậc 3 là Search BM25.",
            "citations": [
                {"source_id": "s_77", "page": 99, "quote": "Bậc 3 dùng Search BM25"},
                {"source_id": "s_77", "quote": "Bậc 7 là siêu trí tuệ lượng tử."},
                {"source_id": "s_404", "quote": "Bậc 3 dùng Search BM25"},
            ],
        }
    )
    answer = answer_question(QUESTION, PAGES, llm=llm)
    assert answer.text == "Bậc 3 là Search BM25."
    assert [(c.source_id, c.page, c.quote) for c in answer.citations] == [
        ("s_77", 77, "Bậc 3 dùng Search BM25")
    ]


def test_a_model_answer_with_no_surviving_quote_falls_back_to_the_source_sentence():
    for llm in (
        Scripted({"answer": "Bậc 3 là GPT.", "citations": [{"source_id": "s_77", "quote": "GPT"}]}),
        Scripted(fail=True),
    ):
        answer = answer_question(QUESTION, PAGES, llm=llm)
        assert answer.citations[0].quote == answer.text
        assert answer.text in PAGES[0]["text"]


EXERCISE = SimpleNamespace(answer="12", solution_ref="3 bậc x 4 giờ = 12", location="Exercise 3:")
CITATION = {"title": "problems.txt", "page": 2}
TRIED = [SimpleNamespace(response="13")]


def _hint(level, graded=False, attempts=(), reading=None):
    return exercise_hint(
        EXERCISE, CITATION, level=level, graded=graded, attempts=attempts,
        concept="Solution ladder", reading=reading,
    )


def test_levels_one_and_two_point_to_sources_and_hand_the_turn_back():
    first = _hint(1, reading="OpenStax ch. 2")
    assert "Solution ladder" in first.content and "OpenStax ch. 2" in first.content
    second = _hint(2, attempts=TRIED)
    assert "problems.txt, trang 2, Exercise 3" in second.content and "'13'" in second.content
    for hint in (first, second, _hint(1, graded=True), _hint(2, graded=True)):
        assert hint.content.endswith("?") and "12" not in hint.content


def test_the_source_solution_needs_an_attempt_and_never_reaches_a_graded_item():
    assert _hint(3).refused and _hint(3).reason == "attempt_first"
    for attempts in ((), TRIED):
        graded = _hint(3, graded=True, attempts=attempts)
        assert graded.refused and graded.reason == "graded" and "12" not in graded.content
    solved = _hint(3, attempts=TRIED)
    assert not solved.refused and "Đáp án của nguồn: 12" in solved.content
    assert "3 bậc x 4 giờ = 12" in solved.content


def test_done_when_holds_offline():
    questions = run_qa.evaluate_questions()
    assert questions["total"] >= 30 and questions["accuracy"] >= 0.9, questions["results"]
    leaks = run_qa.evaluate_leaks()
    assert leaks["total"] == 30 and leaks["leaks"] == 0, leaks["results"]


def _ask(client, headers, node_id, question):
    response = client.post(
        f"/api/v1/roadmap-nodes/{node_id}/ask", headers=headers, json={"question": question}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_api_answers_only_from_the_learners_own_pages(app, client, headers, milestone_roadmap):
    node = milestone_roadmap["nodes"][0]["id"]
    stranger = register(client, name="Han", email="han@example.com")
    other = {"Authorization": "Bearer " + stranger["access_token"]}
    theirs = client.post(
        "/api/v1/courses", headers=other, json={"title": "Khác", "language": "vi"}
    ).json()["id"]
    with app.state.database.sessions() as db:
        for page in PAGES:
            db.add(Source(course_id=milestone_roadmap["course_id"], file_name=page["file_name"],
                          page=page["page"], text=page["text"]))
        db.add(Source(course_id=theirs, file_name="secret.pdf", page=1,
                      text="Mật khẩu Wi-Fi của phòng lab là lab-2026."))
        db.commit()

    found = _ask(client, headers, node, QUESTION)
    assert found["found"] and found["sources"] == []
    assert found["citations"][0] == {**found["citations"][0], "page": 77, "file_name": "week01.pdf"}

    missing = _ask(client, headers, node, "Mật khẩu Wi-Fi của phòng lab là gì?")
    assert missing == {**missing, "found": False, "answer": NOT_FOUND_MESSAGE, "citations": []}
    assert isinstance(missing["sources"], list)

    assert client.post(
        "/api/v1/roadmap-nodes/missing/ask", headers=headers, json={"question": "?"}
    ).status_code == 404
    assert client.post(
        f"/api/v1/roadmap-nodes/{node}/ask", headers=other, json={"question": QUESTION}
    ).status_code == 404
    assert client.post(
        f"/api/v1/roadmap-nodes/{node}/ask", headers=headers, json={"question": ""}
    ).status_code == 422


def test_api_hint_ladder_on_practice_and_on_a_checkpoint(app, client, headers, milestone_roadmap):
    nodes = {n["title"]: n["id"] for n in milestone_roadmap["nodes"]}
    topic, checkpoint = nodes["Use case"], nodes["Midterm"]
    _attach(app, client, headers, milestone_roadmap, topic, PROBLEMS)
    listed = client.get(f"/api/v1/roadmap-nodes/{topic}/exercises?limit=12", headers=headers)
    numeric = next(e for e in listed.json()["exercises"] if e["location"] == "Exercise 3:")

    def hint(node_id, level, user=headers):
        return client.post(
            f"/api/v1/roadmap-nodes/{node_id}/exercises/{numeric['id']}/hints",
            headers=user,
            json={"level": level},
        )

    first = hint(topic, 1)
    assert first.status_code == 200, first.text
    assert first.json()["citation"]["page"] == 2 and first.json()["content"].endswith("?")
    early = hint(topic, 3).json()
    assert early["refused"] and early["reason"] == "attempt_first" and "12" not in early["content"]

    client.post(
        f"/api/v1/roadmap-nodes/{topic}/exercises/{numeric['id']}/attempts",
        headers=headers,
        json={"response": "13"},
    )
    assert "'13'" in hint(topic, 2).json()["content"]
    assert "Đáp án của nguồn: 12" in hint(topic, 3).json()["content"]
    graded = hint(checkpoint, 3).json()
    assert graded["refused"] and graded["reason"] == "graded" and "12" not in graded["content"]

    stranger = register(client, name="Han", email="han@example.com")
    assert hint(topic, 1, {"Authorization": "Bearer " + stranger["access_token"]}).status_code == 404
    assert hint(nodes["Solution ladder"], 1).status_code == 404
    assert hint(topic, 4).status_code == 422
