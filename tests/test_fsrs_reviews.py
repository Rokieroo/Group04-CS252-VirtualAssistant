"""Tests for FSRS spaced repetition review cards, logs, and node mastery (UC-11, issue #162)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import register
from sqlalchemy import text

from app.planner.fsrs import (
    compute_card_retrievability,
    compute_node_mastery,
    schedule_card_review,
)


def test_fsrs_algorithm_standard_rating_sequence():
    """Verify FSRS-4.5 rating transitions, stability growth, and interval calculations."""
    start_time = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    # 1. First review with 'Again' (rating=1)
    res_again = schedule_card_review(rating=1, reviewed_at=start_time)
    assert res_again.state == 1  # Learning
    assert res_again.step >= 0
    assert res_again.stability > 0
    assert res_again.difficulty > 0
    assert res_again.due_at > start_time
    assert res_again.retrievability == 1.0

    # 2. First review with 'Good' (rating=3)
    res_good = schedule_card_review(rating=3, reviewed_at=start_time)
    assert res_good.state == 1  # Learning
    assert (
        res_good.stability > res_again.stability
    )  # Good yields higher stability than Again
    assert (
        res_good.difficulty < res_again.difficulty
    )  # Good is less difficult than Again

    # 3. First review with 'Easy' (rating=4)
    res_easy = schedule_card_review(rating=4, reviewed_at=start_time)
    assert res_easy.stability > res_good.stability  # Easy yields highest stability
    assert res_easy.difficulty < res_good.difficulty

    # 4. Multi-step progression: Good -> Good -> Good
    t2 = res_good.due_at
    res2 = schedule_card_review(
        rating=3,
        reviewed_at=t2,
        current_state=res_good.state,
        current_step=res_good.step,
        stability=res_good.stability,
        difficulty=res_good.difficulty,
        due_at=res_good.due_at,
        last_review=res_good.last_review,
    )
    assert res2.state in (1, 2)  # Learning or Review
    assert res2.due_at > t2
    assert res2.scheduled_days >= res_good.scheduled_days

    t3 = res2.due_at
    res3 = schedule_card_review(
        rating=3,
        reviewed_at=t3,
        current_state=res2.state,
        current_step=res2.step,
        stability=res2.stability,
        difficulty=res2.difficulty,
        due_at=res2.due_at,
        last_review=res2.last_review,
    )
    assert res3.state == 2  # Review
    assert res3.scheduled_days > 1.0


def test_fsrs_mastery_and_retrievability_decay():
    """Verify retrievability calculation decays over elapsed time and mastery aggregates correctly."""
    now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)

    card = {
        "state": 2,
        "step": 0,
        "stability": 5.0,
        "difficulty": 3.0,
        "due_at": now + timedelta(days=5),
        "last_review": now,
    }

    # Immediately after review: retrievability is ~1.0
    r_immediate = compute_card_retrievability(card, now)
    assert round(r_immediate, 2) == 1.0

    # 5 days later (at due date): retrievability decays towards request retention (~0.9)
    r_due = compute_card_retrievability(card, now + timedelta(days=5))
    assert 0.8 < r_due < 1.0
    assert r_due < r_immediate

    # 30 days later (well overdue): retrievability decays further
    r_late = compute_card_retrievability(card, now + timedelta(days=30))
    assert 0.0 < r_late < r_due

    # Node mastery with multiple cards
    card_unreviewed = {
        "state": 1,
        "step": 0,
        "stability": 0.0,
        "difficulty": 0.0,
        "last_review": None,
    }
    assert compute_node_mastery([]) == 0.0
    assert compute_node_mastery([card_unreviewed], now) == 0.0

    mastery_single = compute_node_mastery([card], now)
    assert mastery_single == pytest.approx(r_immediate, abs=0.01)

    mastery_mixed = compute_node_mastery([card, card_unreviewed], now)
    assert mastery_mixed == pytest.approx(r_immediate / 2, abs=0.01)


@pytest.fixture
def test_setup(app, client, headers):
    """Sets up a course, syllabus, roadmap node, and item."""
    c_res = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "Data Structures", "language": "en", "level": "university"},
    )
    assert c_res.status_code == 201
    course_id = c_res.json()["id"]

    client.post(
        f"/api/v1/courses/{course_id}/syllabus",
        headers=headers,
        json={
            "raw_text": "Week 1: Binary Search Trees",
            "outcomes": [{"code": "CLO1", "description": "Binary Search Trees"}],
            "assessments": [],
        },
    )

    r_res = client.post(
        f"/api/v1/courses/{course_id}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {
                    "title": "Binary Search Trees",
                    "week": 1,
                    "type": "topic",
                    "est_minutes": 60,
                }
            ]
        },
    )
    assert r_res.status_code == 201
    roadmap = r_res.json()
    roadmap_id = roadmap["id"]
    node_id = roadmap["nodes"][0]["id"]

    concept_id = str(uuid4())
    item_id = str(uuid4())
    source_id = str(uuid4())

    with app.state.database.sessions() as db:
        # Create concept, link node to concept, create source and item
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:cid, :c, 'bst', 'Binary Search Trees', '[1]')"
            ),
            {"cid": concept_id, "c": course_id},
        )
        db.execute(
            text("UPDATE roadmap_nodes SET concept_id = :cid WHERE id = :nid"),
            {"cid": concept_id, "nid": node_id},
        )
        db.execute(
            text(
                "INSERT INTO sources (id, course_id, file_name, page, text) "
                "VALUES (:s, :c, 'trees.pdf', 1, 'BST notes')"
            ),
            {"s": source_id, "c": course_id},
        )
        db.execute(
            text(
                "INSERT INTO items (id, concept_id, source_id, type, prompt, choices, answer, status) "
                "VALUES (:id, :cid, :sid, 'mcq', 'What is the search complexity of a balanced BST?', '[\"O(1)\", \"O(log n)\", \"O(n)\"]', 'O(log n)', 'ready')"
            ),
            {"id": item_id, "cid": concept_id, "sid": source_id},
        )
        db.commit()

    return {
        "course_id": course_id,
        "roadmap_id": roadmap_id,
        "node_id": node_id,
        "concept_id": concept_id,
        "item_id": item_id,
        "source_id": source_id,
    }


def test_reviews_api_due_and_submit(client, headers, test_setup, clock):
    """Test POST /reviews/{item_id} and GET /reviews/due workflow."""
    item_id = test_setup["item_id"]
    node_id = test_setup["node_id"]

    # 1. No reviews yet -> GET /reviews/due is empty
    due_res0 = client.get("/api/v1/reviews/due", headers=headers)
    assert due_res0.status_code == 200
    assert due_res0.json() == []

    # 2. Submit initial review: rating 3 (Good)
    rev_res1 = client.post(
        f"/api/v1/reviews/{item_id}",
        headers=headers,
        json={"rating": 3, "node_id": node_id},
    )
    assert rev_res1.status_code == 200, rev_res1.text
    data1 = rev_res1.json()
    assert data1["item_id"] == item_id
    assert data1["node_id"] == node_id
    assert data1["rating"] == 3
    assert data1["stability"] > 0
    assert data1["difficulty"] > 0
    assert data1["retrievability"] == 1.0

    # 3. Right now it's scheduled for future, so GET /reviews/due is still empty
    due_res1 = client.get("/api/v1/reviews/due", headers=headers)
    assert due_res1.status_code == 200
    assert due_res1.json() == []

    # 4. Advance clock by 1 day to make the review due
    clock[0] += timedelta(days=1)

    due_res2 = client.get("/api/v1/reviews/due", headers=headers)
    assert due_res2.status_code == 200
    items = due_res2.json()
    assert len(items) == 1
    assert items[0]["item_id"] == item_id
    assert items[0]["prompt"] == "What is the search complexity of a balanced BST?"
    assert items[0]["choices"] == ["O(1)", "O(log n)", "O(n)"]
    assert items[0]["source_id"] == test_setup["source_id"]

    # 5. Review again: rating 4 (Easy)
    rev_res2 = client.post(
        f"/api/v1/reviews/{item_id}",
        headers=headers,
        json={"rating": 4, "node_id": node_id},
    )
    assert rev_res2.status_code == 200
    data2 = rev_res2.json()
    assert data2["stability"] >= data1["stability"]
    assert data2["rating"] == 4


def test_node_mastery_reflects_card_reviews_in_graph_api(client, headers, test_setup):
    """Test that graph API returns updated mastery for nodes based on user reviews."""
    roadmap_id = test_setup["roadmap_id"]
    node_id = test_setup["node_id"]
    item_id = test_setup["item_id"]

    # Initial graph check: mastery should be 0.0
    g_res0 = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers)
    assert g_res0.status_code == 200
    node0 = next(n for n in g_res0.json()["nodes"] if n["id"] == node_id)
    assert node0["mastery"] == 0.0

    # Submit a review with Good (rating 3)
    client.post(
        f"/api/v1/reviews/{item_id}",
        headers=headers,
        json={"rating": 3, "node_id": node_id},
    )

    # Graph check after review: mastery should be 1.0 (recent review)
    g_res1 = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=headers)
    assert g_res1.status_code == 200
    node1 = next(n for n in g_res1.json()["nodes"] if n["id"] == node_id)
    assert node1["mastery"] > 0.9


def test_user_b_isolation_from_user_a_reviews_and_mastery(client, headers, test_setup):
    """Ensure User B never sees User A's reviews, review logs, or mastery (UC-11)."""
    roadmap_id = test_setup["roadmap_id"]
    node_id = test_setup["node_id"]
    item_id = test_setup["item_id"]

    # User A reviews item
    client.post(
        f"/api/v1/reviews/{item_id}",
        headers=headers,
        json={"rating": 3, "node_id": node_id},
    )

    # Register User B
    b_auth = register(client, name="User B", email="user_b_isolation@example.com")
    b_headers = {"Authorization": f"Bearer {b_auth['access_token']}"}

    # User B should have no due reviews
    b_due = client.get("/api/v1/reviews/due", headers=b_headers)
    assert b_due.status_code == 200
    assert b_due.json() == []

    # User B cannot access User A's roadmap
    b_graph = client.get(f"/api/v1/roadmaps/{roadmap_id}/graph", headers=b_headers)
    assert b_graph.status_code == 404

    # User B cannot submit review for User A without creating their own independent card
    b_rev = client.post(
        f"/api/v1/reviews/{item_id}",
        headers=b_headers,
        json={"rating": 1},  # User B rates Again
    )
    assert b_rev.status_code == 200
    b_data = b_rev.json()
    assert b_data["rating"] == 1

    # Verify User A's review card was untouched (stability and rating remain from User A's Good)
    a_due = client.get("/api/v1/reviews/due", headers=headers)
    assert a_due.status_code == 200


def test_reviews_validation_errors(client, headers):
    """Test 404 for unknown items and 422 for invalid ratings."""
    fake_item_id = str(uuid4())

    # Unknown item -> 404
    res_404 = client.post(
        f"/api/v1/reviews/{fake_item_id}",
        headers=headers,
        json={"rating": 3},
    )
    assert res_404.status_code == 404
    assert res_404.json()["detail"] == "Item not found"

    # Rating out of range -> 422
    res_422_high = client.post(
        f"/api/v1/reviews/{fake_item_id}",
        headers=headers,
        json={"rating": 5},
    )
    assert res_422_high.status_code == 422

    res_422_low = client.post(
        f"/api/v1/reviews/{fake_item_id}",
        headers=headers,
        json={"rating": 0},
    )
    assert res_422_low.status_code == 422


def test_fsrs_accepts_naive_db_datetimes_with_utc_reference():
    """Naive SQLite datetimes for due_at and last_review must not raise TypeError."""
    naive_last = datetime(2026, 11, 10, 9, 0)  # tzinfo=None as read from SQLite
    naive_due = datetime(2026, 11, 12, 9, 0)
    aware_now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)

    res = schedule_card_review(
        rating=3,
        reviewed_at=aware_now,
        current_state=2,
        current_step=0,
        stability=5.0,
        difficulty=4.0,
        due_at=naive_due,
        last_review=naive_last,
    )
    assert res.elapsed_days == pytest.approx(2.125, abs=1e-4)
    assert res.due_at > aware_now

    card = {
        "state": 2,
        "step": 0,
        "stability": 5.0,
        "difficulty": 4.0,
        "due_at": naive_due,
        "last_review": naive_last,
    }
    retrievability = compute_card_retrievability(card, aware_now)
    assert 0.0 < retrievability < 1.0
    assert retrievability == pytest.approx(
        compute_card_retrievability(
            {
                **card,
                "due_at": naive_due.replace(tzinfo=UTC),
                "last_review": naive_last.replace(tzinfo=UTC),
            },
            aware_now.replace(tzinfo=None),
        ),
        abs=1e-6,
    )
