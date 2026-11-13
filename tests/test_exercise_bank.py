"""Issue #115 done-when: every question is quoted, cited and owner-scoped; none is written."""

import ast
from pathlib import Path

import pytest
from conftest import register
from pydantic import ValidationError
from sqlalchemy import select
from test_role_catalog import add_resource

from app.catalog.exercises import classify, extract_numbered, order_for
from app.vetting.document import readable_pages
from app.vetting.fetch import FetchResult
from assistant.backend.catalog_models import Exercise
from assistant.backend.catalog_verification import verify_resource
from assistant.backend.models import Resource, Source
from assistant.backend.routes_learning import ExerciseCitationOut

ROOT = Path(__file__).resolve().parents[1]
URL = "https://source0.edu/solution-ladder"
PROBLEMS = """Problems
Exercise 1: Define a use case.
Exercise 2: Explain why a solution ladder has rungs.
Exercise 3: Compute the cost of 3 rungs at 4 hours each.
Answer: 12
Exercise 4: Compare a use case with a user story.
Exercise 5: Prove that the lowest sufficient rung is unique.
Exercise 6: Write a program that prints every rung.
Exercise 7: Design a ladder for a login feature.
Exercise 8: Which rung is cheapest?
A. Manual
B. Script
Answer: A
Exercise 9: Describe an actor.
Exercise 10: Solve the ladder for a search feature.
Exercise 11: Justify skipping a rung.
Exercise 12: List the rungs."""


class Fetcher:
    """Every URL answers with the same page."""

    def __init__(self, body, content_type="text/plain"):
        self.body, self.content_type = body, content_type

    def fetch(self, url):
        return FetchResult(
            url=url, final_url=url, status=200, content_type=self.content_type, body=self.body
        )


def test_labels_come_from_the_source_wording_not_a_model():
    assert classify("Define a use case.") == {
        "type": "short",
        "bloom_level": "remember",
        "difficulty": 1,
    }
    assert classify("Compute 3 x 4.", answer="12")["type"] == "numeric"
    assert classify("Prove it is unique.")["type"] == "proof"
    assert classify("Write a program that prints 1.")["type"] == "code"
    assert classify("Which one?", ["A", "B"])["type"] == "mcq"
    assert classify("So sánh hai cách.")["bloom_level"] == "analyze"
    assert classify("Design a ladder.")["difficulty"] == 5
    items = extract_numbered(PROBLEMS)
    assert len(items) == 12 and {i["type"] for i in items} == {
        "short",
        "numeric",
        "proof",
        "code",
        "mcq",
    }


def test_checkpoints_sample_every_bloom_level_and_practice_climbs():
    pool = [
        {"id": str(n), "difficulty": d, "bloom_level": b}
        for n, (d, b) in enumerate(
            [(1, "remember"), (1, "remember"), (3, "apply"), (4, "analyze")]
        )
    ]
    assert [e["bloom_level"] for e in order_for("checkpoint", pool)[:3]] == [
        "remember",
        "apply",
        "analyze",
    ]
    assert [e["difficulty"] for e in order_for("practice", pool)] == [1, 1, 3, 4]
    assert order_for("checkpoint", []) == []


def test_verified_catalog_pages_yield_their_quoted_exercises(app, client, clock):
    body = PROBLEMS.encode()
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        assert verify_resource(db, resource.id, clock[0], fetcher=Fetcher(body)) == "verified"
        exercises = db.scalars(select(Exercise).where(Exercise.resource_id == resource.id)).all()
        assert len(exercises) == 12
        for exercise in exercises:
            assert exercise.prompt in PROBLEMS and exercise.page is None
            assert exercise.source_hash == db.get(Resource, resource.id).content_hash
        # A link-only license keeps the number and the link, never the wording.
        other = add_resource(db, clock[0], number=1)
        other.license = "CC-BY-NC-SA-4.0"
        db.flush()
        verify_resource(db, other.id, clock[0], fetcher=Fetcher(body))
        linked = db.scalars(select(Exercise).where(Exercise.resource_id == other.id)).all()
        assert linked and all(e.prompt is None and e.location for e in linked)


def test_html_pages_keep_the_line_starts_numbered_exercises_need():
    html = (
        "<html><body><article><h1>Problems</h1>"
        + "".join(f"<p>{line}</p>" for line in PROBLEMS.splitlines()[1:4])
        + "</article></body></html>"
    )
    pages = readable_pages(
        FetchResult(url=URL, status=200, content_type="text/html", body=html.encode())
    )
    assert len(extract_numbered(pages[0])) == 3


@pytest.fixture
def milestone_roadmap(client, headers):
    course = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014", "language": "en"}
    ).json()["id"]
    response = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {"title": "Solution ladder", "week": 1},
                {"title": "Use case", "week": 2},
                {"title": "Midterm", "type": "milestone", "week": 2},
                {"title": "Final", "type": "milestone", "week": 3},
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_each_milestone_has_ten_cited_checkpoint_questions_or_says_insufficient(
    app, client, headers, milestone_roadmap
):
    nodes = {n["title"]: n["id"] for n in milestone_roadmap["nodes"]}
    with app.state.database.sessions() as db:
        source = Source(
            course_id=milestone_roadmap["course_id"],
            file_name="problems.txt",
            page=2,
            text=PROBLEMS,
        )
        db.add(source)
        db.commit()
        source_id = source.id
    path = "/api/v1/roadmap-nodes/{}/exercises?role=checkpoint"
    # Nothing attached yet: report the gap, never fill it.
    for title in ("Midterm", "Final"):
        empty = client.get(path.format(nodes[title]), headers=headers).json()
        assert empty == {**empty, "status": "insufficient", "count": 0, "exercises": []}
    attached = client.post(
        f"/api/v1/roadmap-nodes/{nodes['Use case']}/materials",
        headers=headers,
        json={"source_id": source_id},
    )
    assert attached.status_code == 201, attached.text
    for title in ("Midterm", "Final"):
        result = client.get(path.format(nodes[title]), headers=headers).json()
        assert result["status"] == "ready" and result["count"] == 10, title
        assert len({e["bloom_level"] for e in result["exercises"]}) >= 5
        for exercise in result["exercises"]:
            # Openable citation, word for word on the cited page.
            assert exercise["citation"]["source_id"] == source_id
            assert exercise["citation"]["page"] == 2
            assert exercise["prompt"] in PROBLEMS
            assert all(choice in PROBLEMS for choice in exercise["choices"])
    # The learner's own exercises are visible to nobody else.
    stranger = register(client, name="Han", email="han@example.com")
    other = {"Authorization": "Bearer " + stranger["access_token"]}
    assert client.get(path.format(nodes["Midterm"]), headers=other).status_code == 404


def test_an_exercise_without_a_source_cannot_leave_the_api():
    fields = {"title": "T", "url": None, "institution": None, "license": "private"}
    with pytest.raises(ValidationError):
        ExerciseCitationOut(source_id=None, resource_id=None, **fields)
    with pytest.raises(ValidationError):
        ExerciseCitationOut(source_id="s", resource_id="r", **fields)
    assert ExerciseCitationOut(source_id="s", resource_id=None, **fields)


def test_every_endpoint_that_returns_a_question_carries_its_source(app):
    """The OpenAPI document lists the schema of every endpoint, whatever the router."""
    schemas = app.openapi()["components"]["schemas"]
    returning = {
        name: set(schema.get("properties", {}))
        for name, schema in schemas.items()
        if "prompt" in schema.get("properties", {})
    }
    assert {"ExerciseOut", "ItemOut"} <= set(returning)
    for name, fields in returning.items():
        assert {"source_id", "citation"} & fields, name
    citation = schemas["ExerciseCitationOut"]["properties"]
    assert {"source_id", "resource_id"} <= set(citation)


AUTHORING = (
    "write", "generate", "create", "compose", "invent", "paraphrase", "rephrase",
    "viết", "tạo", "sinh",
)
QUESTION = ("question", "questions", "exercise", "exercises", "quiz", "mcq")


def _docstrings(tree):
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
    }


def test_no_llm_prompt_asks_a_model_to_write_questions():
    """Model instructions are string literals (not docstrings); none asks for a question."""
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                words = node.value.casefold().split()
                if any(a in words for a in AUTHORING) and any(q in words for q in QUESTION):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_exercises_for_node_preloads_sources_and_catalog_without_n_plus_1(
    app, client, headers, clock, milestone_roadmap
):
    from sqlalchemy import event

    from assistant.backend.catalog_models import NodeExercise
    from assistant.backend.exercise_repository import exercises_for_node
    from assistant.backend.models import Course, Roadmap, RoadmapNode

    nodes = {n["title"]: n["id"] for n in milestone_roadmap["nodes"]}
    topic_id = nodes["Solution ladder"]

    with app.state.database.sessions() as db:
        source = Source(
            course_id=milestone_roadmap["course_id"],
            file_name="problems.txt",
            page=2,
            text=PROBLEMS,
        )
        db.add(source)
        resource = add_resource(db, clock[0])
        db.flush()
        source_id = source.id
        verify_resource(db, resource.id, clock[0], fetcher=Fetcher(PROBLEMS.encode()))
        catalog_exercises = db.scalars(
            select(Exercise).where(Exercise.resource_id == resource.id)
        ).all()
        db.add_all(
            [
                NodeExercise(node_id=topic_id, exercise_id=ex.id, role="practice")
                for ex in catalog_exercises
            ]
        )
        db.commit()
        resource_id = resource.id

    attached = client.post(
        f"/api/v1/roadmap-nodes/{topic_id}/materials",
        headers=headers,
        json={"source_id": source_id},
    )
    assert attached.status_code == 201, attached.text

    with app.state.database.sessions() as db:
        node = db.get(RoadmapNode, topic_id)
        roadmap = db.get(Roadmap, milestone_roadmap["id"])
        course = db.get(Course, milestone_roadmap["course_id"])
        assert node is not None and roadmap is not None and course is not None

        source_queries = []
        resource_queries = []

        def _track(conn, cursor, statement, parameters, context, executemany):
            upper = statement.upper()
            if "FROM SOURCES" in upper:
                source_queries.append(statement)
            if "FROM RESOURCES" in upper:
                resource_queries.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            payload = exercises_for_node(db, node, roadmap, course, clock[0], limit=24)
        finally:
            event.remove(engine, "before_cursor_execute", _track)

    assert payload["count"] >= 24
    # 12 private + 12 catalog exercises -> 1 batched Source query and 2 Resource queries total (not 24+).
    assert len(source_queries) == 1
    assert len(resource_queries) <= 2
    assert any(ex["citation"]["source_id"] == source_id for ex in payload["exercises"])
    assert any(ex["citation"]["resource_id"] == resource_id for ex in payload["exercises"])
