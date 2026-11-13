"""Ownership regression tests for FSRS spaced repetition reviews (#162)."""

from __future__ import annotations

from uuid import uuid4

from conftest import register
from sqlalchemy import select, text

from assistant.backend.catalog_models import Exercise, NodeExercise
from assistant.backend.models import Course


def _create_course_and_node(client, auth_headers: dict[str, str], title: str) -> tuple[str, str]:
    course_res = client.post(
        "/api/v1/courses",
        headers=auth_headers,
        json={"title": title, "language": "en", "level": "university"},
    )
    assert course_res.status_code == 201
    course_id = course_res.json()["id"]
    client.post(
        f"/api/v1/courses/{course_id}/syllabus",
        headers=auth_headers,
        json={
            "raw_text": "Week 1: Binary Search Trees",
            "outcomes": [{"code": "CLO1", "description": "Binary Search Trees"}],
            "assessments": [],
        },
    )
    roadmap_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=auth_headers,
        json={
            "nodes": [
                {
                    "title": "Binary Search Trees",
                    "week": 1,
                    "type": "topic",
                    "est_minutes": 45,
                }
            ]
        },
    )
    assert roadmap_res.status_code == 201
    node_id = roadmap_res.json()["nodes"][0]["id"]
    return course_id, node_id


def test_review_fallback_and_explicit_node_id_scoped_to_owner(client, headers, app):
    """Submitting a review must never attach or accept another user's roadmap node_id."""
    course_a, node_a = _create_course_and_node(client, headers, "Owner A Course")

    b_auth = register(client, name="User B", email="user_b_owner@example.com")
    b_headers = {"Authorization": f"Bearer {b_auth['access_token']}"}

    concept_id = str(uuid4())
    concept_ex_id = str(uuid4())
    source_id = str(uuid4())
    exercise_id = str(uuid4())
    concept_item_id = str(uuid4())
    exercise_item_id = str(uuid4())

    with app.state.database.sessions() as db:
        owner_a_id = db.scalar(select(Course.owner_id).where(Course.id == course_a))
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:cid, :c, 'bst-own', 'Binary Search Trees', '[1]')"
            ),
            {"cid": concept_id, "c": course_a},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:cid, :c, 'bst-ex', 'BST Exercises', '[2]')"
            ),
            {"cid": concept_ex_id, "c": course_a},
        )
        db.execute(
            text("UPDATE roadmap_nodes SET concept_id = :cid WHERE id = :nid"),
            {"cid": concept_id, "nid": node_a},
        )
        db.execute(
            text(
                "INSERT INTO sources (id, course_id, file_name, page, text) "
                "VALUES (:s, :c, 'notes.pdf', 1, 'Balanced trees')"
            ),
            {"s": source_id, "c": course_a},
        )
        db.add(
            Exercise(
                id=exercise_id,
                origin="user_material",
                source_id=source_id,
                page=1,
                quote_hash="qh-1",
                source_hash="sh-1",
                owner_id=owner_a_id,
                type="mcq",
                prompt="Height of balanced BST?",
                choices='["O(log n)", "O(n)"]',
                answer="O(log n)",
                license="private",
            )
        )
        db.flush()
        db.add(NodeExercise(node_id=node_a, exercise_id=exercise_id, role="practice"))
        db.execute(
            text(
                "INSERT INTO items (id, concept_id, source_id, type, prompt, choices, answer, status) "
                "VALUES (:id, :cid, :sid, 'mcq', 'Concept Q?', '[\"A\", \"B\"]', 'A', 'ready')"
            ),
            {"id": concept_item_id, "cid": concept_id, "sid": source_id},
        )
        db.execute(
            text(
                "INSERT INTO items (id, concept_id, exercise_id, source_id, type, prompt, choices, answer, status) "
                "VALUES (:id, :cid, :eid, :sid, 'mcq', 'Exercise Q?', '[\"A\", \"B\"]', 'A', 'ready')"
            ),
            {"id": exercise_item_id, "cid": concept_ex_id, "eid": exercise_id, "sid": source_id},
        )
        db.commit()

    # 1. Explicit foreign node_id must be rejected with 404
    explicit_res = client.post(
        f"/api/v1/reviews/{concept_item_id}",
        headers=b_headers,
        json={"rating": 3, "node_id": node_a},
    )
    assert explicit_res.status_code == 404

    # 2. Automatic fallback for User B without an owned node yields node_id=None
    b_concept_res = client.post(
        f"/api/v1/reviews/{concept_item_id}",
        headers=b_headers,
        json={"rating": 3},
    )
    assert b_concept_res.status_code == 200
    assert b_concept_res.json()["node_id"] is None

    b_ex_res = client.post(
        f"/api/v1/reviews/{exercise_item_id}",
        headers=b_headers,
        json={"rating": 3},
    )
    assert b_ex_res.status_code == 200
    assert b_ex_res.json()["node_id"] is None

    # 3. Once User B owns a linked node, automatic fallback resolves to User B's node
    _, node_b = _create_course_and_node(client, b_headers, "Owner B Course")
    with app.state.database.sessions() as db:
        db.execute(
            text("UPDATE roadmap_nodes SET concept_id = :cid WHERE id = :nid"),
            {"cid": concept_id, "nid": node_b},
        )
        db.commit()

    b_owned_res = client.post(
        f"/api/v1/reviews/{concept_item_id}",
        headers=b_headers,
        json={"rating": 4},
    )
    assert b_owned_res.status_code == 200
    assert b_owned_res.json()["node_id"] == node_b
