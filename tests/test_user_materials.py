"""A learner's own material on their roadmap (#114): upload -> mapping job -> review -> delete."""

import json

import pytest
from conftest import register
from sqlalchemy import func, select
from test_document_formats import pptx

from app.llm import FakeLLM
from assistant.backend import jobs, material_repository
from assistant.backend.catalog_models import Exercise, NodeMaterial
from assistant.backend.models import Job, Resource, Source

DECK = pptx(
    "Week 1",
    "Problem framing: stakeholders",
    "Problem framing traps",
    "Use case diagrams: actors",
    "Exercise 1: Draw the use case diagram of the library.",
)
# Nodes are numbered by week for the model: N1 framing (week 1), N2 use cases (week 2).
SEGMENTS = {
    "segments": [
        {"page_from": 1, "page_to": 1, "node": "none", "confidence": 1},
        {"page_from": 2, "page_to": 3, "node": "N1", "confidence": 0.9},
        {"page_from": 4, "page_to": 5, "node": "N2", "confidence": 0.9},
    ]
}


@pytest.fixture
def course(client, headers):
    return client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014", "language": "en"}
    ).json()["id"]


def generate(client, headers, course):
    response = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={"nodes": [{"title": "Problem framing", "week": 1},
                        {"title": "Use case diagrams", "week": 2}]},
    )
    assert response.status_code == 201, response.text
    return [node["id"] for node in response.json()["nodes"]]


def upload(client, headers, course, name="week1.pptx", data=DECK):
    return client.post(
        f"/api/v1/courses/{course}/sources",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
    )


def run_jobs(app):
    results = []
    while (job_id := jobs.run_once(app.state.database.sessions, app.state.now())) is not None:
        with app.state.database.sessions() as db:
            results.append(json.loads(db.get(Job, job_id).result))
    return results


def materials(client, headers, node):
    response = client.get(f"/api/v1/roadmap-nodes/{node}/materials", headers=headers)
    assert response.status_code == 200, response.text
    return [(f["status"], [p["page"] for p in f["pages"]]) for f in response.json()["files"]]


def source_ids(app, course):
    with app.state.database.sessions() as db:
        return {s.page: s.id for s in db.scalars(select(Source).where(Source.course_id == course))}


def test_uploaded_slides_are_mapped_and_shown_before_catalog_sources(
    app, client, headers, course, monkeypatch
):
    monkeypatch.setattr(material_repository, "get_client", lambda: FakeLLM(
        {"material_outline": json.dumps(SEGMENTS)}))
    framing, use_cases = generate(client, headers, course)
    response = upload(client, headers, course)
    assert response.status_code == 201, response.text
    assert response.json()["mapping_job_id"]
    assert run_jobs(app) == [{"status": "done", "files": 1, "attached": 4, "suggested": 0}]
    assert materials(client, headers, framing) == [("attached", [2, 3])]
    assert materials(client, headers, use_cases) == [("attached", [4, 5])]
    sources = client.get(f"/api/v1/concepts/{framing}/sources", headers=headers).json()
    first = sources["sources"][0]
    assert (first["kind"], first["title"], first["pages"]) == ("user_material", "week1.pptx", [2, 3])
    assert first["reason"] == "Tài liệu của bạn" and sources["user_material_count"] == 1
    # The quoted exercise of page 5 reaches the node its page is attached to.
    exercises = client.get(f"/api/v1/roadmap-nodes/{use_cases}/exercises", headers=headers)
    assert [e["citation"]["page"] for e in exercises.json()["exercises"]] == [5]
    with app.state.database.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Resource)) == 0  # never shared


def test_unsure_pages_wait_for_one_tap_and_decisions_survive_remapping(
    app, client, headers, course
):
    framing, use_cases = generate(client, headers, course)
    upload(client, headers, course)
    [result] = run_jobs(app)  # offline: lexical evidence only
    assert result["attached"] == 0 and result["suggested"] == 5  # every page with text
    assert materials(client, headers, framing)[0][0] == "suggested"
    sources = client.get(f"/api/v1/concepts/{framing}/sources", headers=headers).json()
    assert sources["user_material_count"] == 0  # not shown until confirmed
    pages = source_ids(app, course)
    for node, page, attached in [(framing, 2, True), (use_cases, 4, False)]:
        response = client.put(
            f"/api/v1/roadmap-nodes/{node}/materials/{pages[page]}",
            headers=headers,
            json={"attached": attached},
        )
        assert response.status_code == 200, response.text
        assert response.json()["method"] == "manual"
    with app.state.database.sessions() as db:
        material_repository.enqueue_mapping(
            db, db.get(material_repository.Course, course), app.state.now()
        )
        db.commit()
    run_jobs(app)
    assert ("attached", [2]) in materials(client, headers, framing)
    assert all(4 not in pages for _, pages in materials(client, headers, use_cases))


def test_another_learner_never_sees_or_changes_my_material(
    app, client, headers, course, monkeypatch
):
    monkeypatch.setattr(material_repository, "get_client", lambda: FakeLLM(
        {"material_outline": json.dumps(SEGMENTS)}))
    framing, _ = generate(client, headers, course)
    upload(client, headers, course)
    run_jobs(app)
    page = source_ids(app, course)[2]
    other = {"Authorization": "Bearer " + register(client, "Han", "han@example.com")["access_token"]}
    theirs = client.post(
        "/api/v1/courses", headers=other, json={"title": "CSC10014", "language": "en"}
    ).json()["id"]  # same course title, different owner
    assert client.get(f"/api/v1/roadmap-nodes/{framing}/materials", headers=other).status_code == 404
    assert client.get(f"/api/v1/concepts/{framing}/sources", headers=other).status_code == 404
    assert client.put(
        f"/api/v1/roadmap-nodes/{framing}/materials/{page}", headers=other, json={"attached": False}
    ).status_code == 404
    assert client.delete(
        f"/api/v1/courses/{course}/sources/week1.pptx", headers=other
    ).status_code == 404
    their_node = generate(client, other, theirs)[0]
    assert client.post(
        f"/api/v1/roadmap-nodes/{their_node}/materials", headers=other, json={"source_id": page}
    ).status_code == 404
    assert client.get(f"/api/v1/courses/{theirs}/sources", headers=other).json() == []
    assert materials(client, headers, framing) == [("attached", [2, 3])]


def test_deleting_a_file_removes_its_pages_links_and_exercises(
    app, client, headers, course, monkeypatch
):
    monkeypatch.setattr(material_repository, "get_client", lambda: FakeLLM(
        {"material_outline": json.dumps(SEGMENTS)}))
    framing, _ = generate(client, headers, course)
    upload(client, headers, course)
    run_jobs(app)
    with app.state.database.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Exercise)) == 1
    endpoint = f"/api/v1/courses/{course}/sources/week1.pptx"
    assert client.delete(endpoint, headers=headers).status_code == 204
    assert client.delete(endpoint, headers=headers).status_code == 404
    with app.state.database.sessions() as db:
        for table in (Source, NodeMaterial, Exercise):
            assert db.scalar(select(func.count()).select_from(table)) == 0
    assert materials(client, headers, framing) == []


def test_material_uploaded_before_the_roadmap_is_mapped_when_it_is_generated(
    app, client, headers, course
):
    assert upload(client, headers, course).json()["mapping_job_id"] is None
    generate(client, headers, course)
    with app.state.database.sessions() as db:
        kinds = list(db.scalars(select(Job.kind)))
    assert "map_materials" in kinds
    assert run_jobs(app)[-1]["files"] == 1


def test_goals_without_a_syllabus_become_a_draft_that_builds_a_roadmap(client, headers, course):
    pasted = "Goals:\n- Recursion\n- Sorting: quicksort, mergesort\n1. Binary trees\n- recursion"
    response = client.post(
        f"/api/v1/courses/{course}/syllabus:parse",
        headers=headers,
        json={"text": pasted, "kind": "goals"},
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["status"] == "draft" and draft["can_confirm"]
    assert [(w["week"], w["topics"]) for w in draft["parsed"]["weeks"]] == [
        (1, ["Recursion"]),
        (2, ["Sorting: quicksort, mergesort"]),
        (3, ["Binary trees"]),
    ]
    assert "estimated_schedule" in {w["code"] for w in draft["warnings"]}
    for bad in ({"text": "Goals:\n-\n", "kind": "goals"}, {"file_name": "x.pdf", "kind": "goals"}):
        assert client.post(
            f"/api/v1/courses/{course}/syllabus:parse", headers=headers, json=bad
        ).status_code == 422
    raw = "\n\n".join(draft["source_pages"].values())
    saved = client.post(
        f"/api/v1/courses/{course}/syllabus", headers=headers, json={"raw_text": raw}
    )
    assert saved.status_code == 201, saved.text
    roadmap = client.post(f"/api/v1/courses/{course}/roadmap:generate", headers=headers)
    assert roadmap.status_code == 201, roadmap.text
    # The same week-line derivation as an uploaded syllabus (commas split topics).
    assert [(n["week"], n["title"]) for n in roadmap.json()["nodes"]] == [
        (1, "Recursion"), (2, "Sorting: quicksort"), (2, "mergesort"), (3, "Binary trees"),
    ]
