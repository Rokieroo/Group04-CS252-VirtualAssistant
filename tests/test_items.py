"""#115 supersedes #10: source extraction, never AI-authored questions."""

import inspect
import json

import pytest
from conftest import register
from sqlalchemy import text

from app.catalog.exercises import exact, extract_numbered, from_offsets
from app.items.find import find_items, parse_items, pick_pages, save_items

TEXT = """Solution ladder
Exercise 1: Which rung uses search?
A. Rules
B. Search
Answer: B. Search
Exercise 2: Explain the lowest sufficient rung.
"""
SOURCES = [{"id": "s1", "page": 1, "text": TEXT}]
CONCEPT = {"title": "Solution ladder", "summary": "", "source_pages": [1]}


def test_extracts_only_verbatim_numbered_questions_and_official_answers():
    items = extract_numbered(TEXT)
    assert len(items) == 2
    assert items[0]["prompt"] == "Which rung uses search?"
    assert items[0]["choices"] == ["Rules", "Search"]
    assert items[0]["answer"] == "B. Search"
    assert items[1]["answer"] is None
    assert all(exact(i, TEXT) for i in items)
    assert extract_numbered("A lecture with no exercises.") == []


def test_finding_items_takes_no_model_and_uses_cited_pages():
    assert "llm" not in inspect.signature(find_items).parameters
    assert len(find_items(CONCEPT, SOURCES)) == 2
    assert pick_pages(CONCEPT, SOURCES)[0]["id"] == "s1"
    assert (
        find_items({**CONCEPT, "source_pages": [], "title": "zzzz"}, SOURCES)
        == []
    )


def test_cited_pages_are_matched_in_their_own_file():
    decks = [{**SOURCES[0], "file_name": "week01.pdf"},
             {"id": "s2", "file_name": "week02.pdf", "page": 1, "text": TEXT}]
    cited = {**CONCEPT, "source_refs": [{"file_name": "week02.pdf", "page": 1}]}
    assert [p["id"] for p in pick_pages(cited, decks)] == ["s2"]
    # Concepts saved before files were recorded still cite page 1 of every file.
    assert {p["id"] for p in pick_pages(CONCEPT, decks)} == {"s1", "s2"}


@pytest.mark.parametrize("index", range(10))
def test_ten_fabricated_questions_are_rejected(index):
    proposal = {
        "source_id": "s1",
        "prompt": f"Invented question {index}",
        "answer": "invented",
    }
    assert parse_items(json.dumps({"items": [proposal]}), {"s1": TEXT}) == []
    assert not exact(proposal, TEXT)


@pytest.mark.parametrize(
    "span",
    [
        {"start": True, "end": 5},
        {"start": -1, "end": 8},
        {"start": 0.5, "end": 10},
        {"start": 0, "end": 9999},
        {"start": 0, "end": 1, "prompt": "fake"},
    ],
)
def test_offsets_cannot_supply_prose_or_escape_source_bounds(span):
    assert from_offsets(TEXT, [span]) == []


def test_offset_proposals_are_sliced_from_evidence():
    start = TEXT.index("Exercise 1")
    result = parse_items(
        json.dumps({"items": [{"source_id": "s1", "start": start, "end": len(TEXT)}]}),
        {"s1": TEXT},
    )
    assert len(result) == 2
    assert (
        parse_items(
            json.dumps(
                {"items": [{"source_id": "s1", "start": start, "end": len(TEXT)}]}
            ),
            {"s1"},
        )
        == []
    )


@pytest.fixture
def course(client, headers, app):
    course_id = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014"}
    ).json()["id"]
    with app.state.database.sessions() as db:
        db.execute(
            text(
                "INSERT INTO sources (id,course_id,file_name,page,text) VALUES ('s1',:c,'exercises.txt',1,:t)"
            ),
            {"c": course_id, "t": TEXT},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id,course_id,slug,title,source_pages) VALUES ('c1',:c,'solution-ladder','Solution ladder','[1]')"
            ),
            {"c": course_id},
        )
        db.commit()
    return course_id


def test_saved_items_have_exercise_provenance_and_are_idempotent(
    app, client, headers, course
):
    with app.state.database.sessions() as db:
        saved = save_items(db, "c1", find_items(CONCEPT, SOURCES))
        db.commit()
        assert len(saved) == 2
        assert save_items(db, "c1", find_items(CONCEPT, SOURCES)) == []
        assert (
            db.scalar(text("SELECT count(*) FROM items WHERE exercise_id IS NULL")) == 0
        )
    endpoint = f"/api/v1/courses/{course}/concepts/c1/items"
    response = client.get(endpoint, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2
    with app.state.database.sessions() as db:
        db.execute(text("UPDATE sources SET text='Replacement lecture' WHERE id='s1'"))
        db.commit()
    assert client.get(endpoint, headers=headers).json() == []


def test_find_endpoint_quotes_without_ai_and_hides_other_users(
    client, headers, course
):
    endpoint = f"/api/v1/courses/{course}/concepts/c1/items"
    response = client.post(endpoint + ":find", headers=headers)
    assert response.status_code == 201, response.text
    assert len(response.json()) == 2
    for item in response.json():
        assert item["origin"] == "user_material" and item["source_id"] == "s1"
        assert item["location"].startswith("Exercise") and item["prompt"] in TEXT
    # The deprecated alias still answers for one release, with the same items.
    alias = client.post(endpoint + ":generate", headers=headers)
    assert alias.status_code == 201 and alias.json() == response.json()
    other = {
        "Authorization": "Bearer "
        + register(client, "Lan", "lan@example.com")["access_token"]
    }
    assert client.get(endpoint, headers=other).status_code == 404
    assert client.post(endpoint + ":find", headers=other).status_code == 404
    assert client.get(endpoint).status_code == 401


def test_no_exercises_means_insufficient_not_generated_content(
    app, client, headers, course
):
    with app.state.database.sessions() as db:
        db.execute(text("UPDATE sources SET text='Lecture only' WHERE id='s1'"))
        db.commit()
    response = client.post(
        f"/api/v1/courses/{course}/concepts/c1/items:find", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "exercise_bank_insufficient"
