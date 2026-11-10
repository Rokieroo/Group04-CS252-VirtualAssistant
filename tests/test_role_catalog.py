"""Role issues #96/#99/#100/#102/#115: invariants and owner-scoped integration."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from conftest import register
from sqlalchemy import func, select

from app.catalog.institutions import (
    authority_for,
    build_registry,
    parent_domains,
    read_registry,
    seed_institutions,
    write_registry,
)
from app.catalog.taxonomy import encode, save_tags, subjects, tag_node, tag_resource
from app.llm import FakeLLM
from app.roadmap.graph import topological_sort, would_create_cycle
from app.search.catalog import CatalogSearch
from assistant.backend.catalog_models import (
    Institution,
    NodeExercise,
    ResourceVerification,
    RoadmapEdge,
)
from assistant.backend.catalog_repository import (
    verified_resources,
)
from assistant.backend.database import Database
from assistant.backend.exercise_repository import import_catalog_exercise
from assistant.backend.models import (
    Course,
    Resource,
    Roadmap,
    RoadmapNode,
    Source,
    User,
)
from assistant.backend.roadmap_repository import CycleError, add_roadmap_edge

ROOT = Path(__file__).resolve().parents[1]


def test_registry_is_reproducible_and_domain_matching_is_not_substring(tmp_path):
    oa = [
        {
            "id": "https://openalex.org/I2",
            "type": "education",
            "works_count": 1200,
            "ror": "https://ror.org/02",
            "homepage_url": "https://www.b.edu",
            "display_name": "B",
            "country_code": "US",
            "cited_by_count": 4,
            "summary_stats": {"h_index": 50},
        },
        {
            "id": "https://openalex.org/I1",
            "type": "education",
            "works_count": 1300,
            "ror": "https://ror.org/01",
            "homepage_url": "https://a.edu",
            "display_name": "A",
            "country_code": "US",
            "cited_by_count": 4,
            "summary_stats": {"h_index": 50},
        },
    ]
    ror = [
        {"id": "https://ror.org/01", "domains": ["a.edu"]},
        {"id": "https://ror.org/02", "domains": ["b.edu"]},
    ]
    options = {
        "snapshot_date": "2026-11-05",
        "openalex_version": "fixture-v1",
        "ror_version": "fixture-v2",
    }
    first = build_registry(oa, ror, **options)
    second = build_registry(list(reversed(oa)), list(reversed(ror)), **options)
    write_registry(first, tmp_path / "a.csv")
    write_registry(second, tmp_path / "b.csv")
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert json.loads(first[0]["rank_signal"])["rank"] == 1
    assert authority_for("https://learn.a.edu/x", first) == 1.0
    assert authority_for("https://a.edu.evil.example/x", first) == 0.4
    assert authority_for("https://nota.edu/x", first) == 0.4
    assert parent_domains("https://www.learn.a.edu/x") == ["learn.a.edu", "a.edu", "edu"]
    assert "a.edu" not in parent_domains("https://a.edu.evil.example/x")
    assert parent_domains("") == []
    oa[0]["homepage_url"] = "https://b.edu.evil.example"
    assert len(build_registry(oa, ror, **options)) == 1


def test_bundled_registry_has_500_real_ror_domains_and_valid_metadata():
    rows = read_registry(ROOT / "data/catalog/institutions.csv")
    assert len(rows) >= 500
    assert all(r["ror_id"].startswith(("https://ror.org/", "vn-k12:")) for r in rows)
    assert all(
        json.loads(r["rank_signal"])["ror_version"].startswith("10.5281/zenodo.")
        for r in rows
    )


def test_bilingual_taxonomy_covers_csc10014_and_flags_unknowns():
    assert tag_resource({"title": "Phân rã tác vụ"})[0].subject_id == "ct.decomposition"
    assert tag_node({"title": "Solution ladder"})[0].subject_id == "ct.ladder"
    text = (ROOT / "eval/syllabus/01_csc10014_problem_framing.txt").read_text(
        encoding="utf-8"
    )
    topics = [
        line.split(":", 1)[1] for line in text.splitlines() if line.startswith("Week ")
    ]
    assert all(tag_node({"title": title}, course="CSC10014") for title in topics)
    assert tag_node({"title": "unrecognizable zzzzz"})[0].needs_review
    assert len(encode("Solution ladder")) == 256
    assert encode("Solution ladder") == encode("Solution ladder")
    assert {r["depth"] for r in subjects()} == {1, 2, 3}


def test_own_text_names_topics_and_the_longest_phrase_wins():
    # A resource's description names its topic, below a title match but accepted.
    [tag] = tag_resource({"title": "Lecture 4", "description": "AVL tree rotations"})
    assert (tag.subject_id, tag.method, tag.needs_review) == ("ds.trees", "rule:text", False)
    # Course context alone names the subject, never a topic.
    assert [t.subject_id for t in tag_resource({"title": "Lecture 4", "course": "CS201"})] == [
        "ds"
    ]
    # "relational algebra" is SQL, not the "algebra" inside it; plurals and CamelCase match.
    assert [t.subject_id for t in tag_resource({"title": "Relational algebra"})] == ["db.sql"]
    assert [t.subject_id for t in tag_resource({"title": "Binary heaps"})] == ["ds.trees"]
    assert [t.subject_id for t in tag_resource({"title": "/TestDrivenDevelopment"})] == [
        "se.testing"
    ]
    # An assessment node takes the topics of the nodes it covers.
    tags = tag_node({"title": "Midterm exam"}, course="CSC10014", covers=["Solution ladder"])
    assert [(t.subject_id, t.needs_review) for t in tags] == [("ct.ladder", False)]


def test_llm_decides_only_unsure_resources_and_only_with_known_labels():
    answer = json.dumps({"subjects": ["ds.trees", "made.up", "ds.trees"], "confidence": 0.8})
    llm = FakeLLM({"zzzz": answer})
    [tag] = tag_resource({"title": "zzzz qqqq"}, llm=llm)
    assert (tag.subject_id, tag.method, tag.needs_review) == ("ds.trees", "llm", False)
    # A rule match is sure already: no call.
    assert tag_resource({"title": "Binary heaps"}, llm=llm)[0].method == "rule:title"
    assert llm.calls == 1
    # Low self-reported confidence still goes to review; bad answers keep the vector tag.
    low = FakeLLM({"zzzz": json.dumps({"subjects": ["ds.trees"], "confidence": 0.3})})
    assert tag_resource({"title": "zzzz"}, llm=low)[0].needs_review
    for bad in ("not json", "[]", '{"subjects": ["made.up"], "confidence": 1}'):
        [tag] = tag_resource({"title": "zzzz"}, llm=FakeLLM({"zzzz": bad}))
        assert tag.method != "llm" and tag.needs_review


@pytest.fixture
def roadmap(client, headers):
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
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_graph_edges_and_layout_are_persisted_and_owner_scoped(
    app, client, headers, roadmap
):
    first, second = roadmap["nodes"]
    endpoint = f"/api/v1/roadmaps/{roadmap['id']}"
    with app.state.database.sessions() as db:
        edges = list(db.scalars(select(RoadmapEdge)))
        assert [(e.parent_id, e.child_id, e.kind, e.origin) for e in edges] == [
            (first["id"], second["id"], "soft", "week_order")
        ]
    response = client.post(
        endpoint + "/edges",
        headers=headers,
        json={"parent_id": second["id"], "child_id": first["id"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["path"] == [
        second["id"],
        first["id"],
        second["id"],
    ]
    assert (
        client.post(
            endpoint + "/edges",
            headers=headers,
            json={"parent_id": first["id"], "child_id": first["id"]},
        ).status_code
        == 409
    )
    payload = {
        "positions": [{"node_id": first["id"], "x": 12.5, "y": -40, "pinned": True}]
    }
    assert (
        client.put(endpoint + "/layout", headers=headers, json=payload).status_code
        == 200
    )
    assert client.get(endpoint + "/layout", headers=headers).json() == payload
    other = {
        "Authorization": "Bearer "
        + register(client, "Other", "other@example.com")["access_token"]
    }
    assert client.get(endpoint + "/layout", headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/concepts/{first['id']}/sources", headers=other).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/roadmap-nodes/{first['id']}/exercises", headers=other
        ).status_code
        == 404
    )


def add_resource(db, now, *, number=0, status="verified", days=0):
    url = f"https://source{number}.edu/solution-ladder"
    institution = Institution(
        ror_id=f"fixture:{number}",
        name=f"School {number}",
        country="US",
        domain=f"source{number}.edu",
        tier=1,
    )
    db.add(institution)
    row = Resource(
        url=url,
        canonical_url=url,
        title="Solution ladder",
        lang="en",
        kind="reading",
        format="reading",
        license="CC-BY-4.0",
        is_free=True,
        verification_status=status,
        content_hash=hashlib.sha256(b"Exercise 1: Solution ladder?").hexdigest(),
        domain=f"source{number}.edu",
    )
    db.add(row)
    db.flush()
    save_tags(db, "resource", row.id, tag_resource({"title": row.title}), row.title)
    for check in ("fetch", "domain", "license", "metadata"):
        db.add(
            ResourceVerification(
                checked_by="test:offline",
                resource_id=row.id,
                check_name=check,
                result="pass",
                checked_at=now - timedelta(days=days),
            )
        )
    db.flush()
    return row


def test_sources_are_private_first_and_never_pending_stale_or_rejected(
    app, client, headers, roadmap, clock
):
    node = roadmap["nodes"][0]["id"]
    course = roadmap["course_id"]
    with app.state.database.sessions() as db:
        for number, status, days in [
            (0, "verified", 0),
            (1, "pending", 0),
            (2, "rejected", 0),
            (3, "verified", 31),
        ]:
            add_resource(db, clock[0], number=number, status=status, days=days)
        source = Source(
            course_id=course,
            file_name="my-notes.txt",
            page=3,
            text="Exercise 1: Select the lowest sufficient rung.",
        )
        db.add(source)
        db.commit()
        source_id = source.id
    assert (
        client.post(
            f"/api/v1/roadmap-nodes/{node}/materials",
            headers=headers,
            json={"source_id": source_id},
        ).status_code
        == 201
    )
    response = client.get(f"/api/v1/concepts/{node}/sources", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    assert [r["kind"] for r in result["sources"]] == ["user_material", "web"]
    assert result["sources"][0]["source_id"] == source_id
    assert result["sources"][1]["institution"] == "School 0"
    with app.state.database.sessions() as db:
        catalog = CatalogSearch(session=db, now=clock[0])
        assert len(catalog.search("Solution ladder", lang="en")) == 1
        assert (
            seed_institutions(db, read_registry(ROOT / "data/catalog/institutions.csv"))
            >= 500
        )
        assert (
            seed_institutions(db, read_registry(ROOT / "data/catalog/institutions.csv"))
            >= 500
        )
        db.commit()
    summary = client.get(
        f"/api/v1/roadmaps/{roadmap['id']}/sources:summary", headers=headers
    ).json()
    assert len(summary["nodes"]) == 2
    assert all("sources" not in n for n in summary["nodes"])
    exercises = client.get(
        f"/api/v1/roadmap-nodes/{node}/exercises?role=checkpoint", headers=headers
    ).json()
    assert exercises["status"] == "insufficient" and exercises["count"] == 1
    assert exercises["exercises"][0]["citation"]["source_id"] == source_id
    assert not exercises["exercises"][0]["auto_grade"]
    assert "answer" not in exercises["exercises"][0]


def test_own_material_hides_what_it_teaches_and_five_sources_is_the_most(
    app, client, headers, roadmap, clock, monkeypatch
):
    from app.catalog import taxonomy

    node, course = roadmap["nodes"][0]["id"], roadmap["course_id"]
    with app.state.database.sessions() as db:
        for number in range(3):
            add_resource(db, clock[0], number=number)  # verified, all on the ladder
        ladder = Source(course_id=course, file_name="ladder.txt", page=1,
                        text="Solution ladder: pick the lowest sufficient rung")
        notes = [Source(course_id=course, file_name=f"notes{i}.txt", page=1,
                        text="Use case diagrams and actors") for i in range(4)]
        db.add_all([ladder, *notes])
        db.commit()
        ladder_id, note_ids = ladder.id, [note.id for note in notes]

    def attach(source_id, attached=True):
        response = client.put(f"/api/v1/roadmap-nodes/{node}/materials/{source_id}",
                              headers=headers, json={"attached": attached})
        assert response.status_code == 200, response.text

    def kinds():
        # Pages were tagged on attach; reading sources never tags private text again.
        with monkeypatch.context() as patch:
            patch.setattr(taxonomy, "_tags", lambda *a, **k: pytest.fail("tagged on read"))
            response = client.get(f"/api/v1/concepts/{node}/sources", headers=headers)
        assert response.status_code == 200, response.text
        return [r["kind"] for r in response.json()["sources"]]

    attach(ladder_id)
    assert kinds() == ["user_material"]  # the learner's page already teaches the ladder
    attach(ladder_id, attached=False)
    for source_id in note_ids:
        attach(source_id)
    assert kinds() == ["user_material"] * 4 + ["web"]  # own files first, 5 in all


def test_latest_failed_check_and_changed_source_invalidate_exercises(
    app, client, headers, roadmap, clock
):
    node_id = roadmap["nodes"][0]["id"]
    source_text = "Exercise 1: Solution ladder?"
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        item = {
            "prompt": "Solution ladder?",
            "choices": [],
            "answer": None,
            "location": "Exercise 1",
            "type": "short",
        }
        exercise = import_catalog_exercise(db, resource.id, source_text, item, clock[0])
        db.add(NodeExercise(node_id=node_id, exercise_id=exercise.id, role="practice"))
        db.commit()
        assert exercise.prompt == item["prompt"]
        resource_id = resource.id
    path = f"/api/v1/roadmap-nodes/{node_id}/exercises"
    assert client.get(path, headers=headers).json()["count"] == 1
    with app.state.database.sessions() as db:
        db.add(
            ResourceVerification(
                checked_by="test:offline",
                resource_id=resource_id,
                check_name="domain",
                result="fail",
                checked_at=clock[0] + timedelta(seconds=1),
            )
        )
        db.commit()
    clock[0] += timedelta(seconds=2)
    assert client.get(path, headers=headers).json()["count"] == 0
    with app.state.database.sessions() as db:
        assert verified_resources(db, clock[0]) == []


def test_catalog_exercises_reject_fabrication_and_respect_link_only_licenses(
    app, client, headers, roadmap, clock
):
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        for number in range(10):
            with pytest.raises(ValueError, match="exercise_not_in_source"):
                import_catalog_exercise(
                    db,
                    resource.id,
                    "Exercise 1: Solution ladder?",
                    {"prompt": f"Fabricated {number}", "location": "Exercise 1"},
                    clock[0],
                )
        resource.license = "CC-BY-NC-SA-4.0"
        db.flush()
        exercise = import_catalog_exercise(
            db,
            resource.id,
            "Exercise 1: Solution ladder?",
            {"prompt": "Solution ladder?", "location": "Exercise 1"},
            clock[0],
        )
        assert (
            exercise.prompt is None
            and exercise.answer is None
            and exercise.choices is None
        )
        assert exercise.location == "Exercise 1"


def test_only_one_concurrent_opposite_edge_commits(tmp_path, database_url):
    database = Database(
        "sqlite:///" + (tmp_path / "race.db").as_posix()
        if database_url == "sqlite://"
        else database_url
    )
    database.create_schema()
    with database.sessions() as db:
        user = User(email="race@example.com", password_hash="test", name="Race")
        db.add(user)
        db.flush()
        course = Course(owner_id=user.id, title="Graph")
        db.add(course)
        db.flush()
        roadmap = Roadmap(course_id=course.id, user_id=user.id, title="Graph")
        db.add(roadmap)
        db.flush()
        db.add_all(
            [
                RoadmapNode(id="a", roadmap_id=roadmap.id, type="topic", title="A"),
                RoadmapNode(id="b", roadmap_id=roadmap.id, type="topic", title="B"),
            ]
        )
        db.commit()
        identifier = roadmap.id
    barrier = Barrier(2)

    def add(parent, child):
        with database.sessions() as db:
            barrier.wait(timeout=5)
            try:
                add_roadmap_edge(db, identifier, parent, child)
                db.commit()
                return "saved"
            except CycleError:
                db.rollback()
                return "cycle"

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(add, "a", "b")
        b = executor.submit(add, "b", "a")
        assert sorted([a.result(timeout=10), b.result(timeout=10)]) == [
            "cycle",
            "saved",
        ]
    with database.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RoadmapEdge)) == 1
    database.engine.dispose()


def test_graph_algorithm_accepts_300_nodes_and_rejects_back_edge():
    edges = [(str(i), str(i + 1)) for i in range(299)]
    path = would_create_cycle(edges, "299", "0")
    assert path[0] == path[-1] == "299" and len(path) == 301
    assert would_create_cycle(edges, "0", "299") is None
    assert len(topological_sort([str(i) for i in range(300)], edges)) == 300


def test_migration_roundtrip_preserves_existing_reviews_and_resource_links(tmp_path):
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command

    database = Database("sqlite:///" + (tmp_path / "upgrade.db").as_posix())
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with database.engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0007_search_metrics")
        statements = [
            "INSERT INTO users (id,email,password_hash) VALUES ('u','u@example.com','test')",
            "INSERT INTO courses (id,owner_id,title) VALUES ('c','u','Course')",
            "INSERT INTO sources (id,course_id,file_name,page,text) VALUES ('s','c','notes',1,'source')",
            "INSERT INTO concepts (id,course_id,slug,title) VALUES ('k','c','topic','Topic')",
            "INSERT INTO items (id,concept_id,source_id,type,prompt,answer,status) VALUES ('i','k','s','short','old question','old answer','approved')",
            "INSERT INTO cards (user_id,item_id,fsrs_state,due_at) VALUES ('u','i','{}','2030-01-01')",
            "INSERT INTO reviews (id,user_id,item_id,rating) VALUES ('v','u','i',3)",
            "INSERT INTO roadmaps (id,course_id,user_id,title) VALUES ('r','c','u','Roadmap')",
            "INSERT INTO roadmap_nodes (id,roadmap_id,type,title) VALUES ('n','r','topic','Topic')",
            "INSERT INTO resources (id,url,title) VALUES ('w','https://example.edu','Source')",
            "INSERT INTO node_resources (node_id,resource_id) VALUES ('n','w')",
        ]
        for statement in statements:
            conn.execute(text(statement))
        command.upgrade(config, "head")
        for table in ("cards", "reviews", "node_resources"):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        assert conn.scalar(text("SELECT status FROM items WHERE id='i'")) == "rejected"
        command.downgrade(config, "0007_search_metrics")
        for table in ("cards", "reviews", "node_resources"):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        command.upgrade(config, "head")
    database.engine.dispose()


def test_generated_graph_links_concepts_and_keeps_strict_edges(app, client, headers):
    from sqlalchemy import text

    from assistant.backend.catalog_models import Concept

    course = client.post(
        "/api/v1/courses", headers=headers, json={"title": "Graph"}
    ).json()["id"]
    with app.state.database.sessions() as db:
        db.add_all(
            [
                Concept(id="a", course_id=course, slug="a", title="Algebra"),
                Concept(id="b", course_id=course, slug="b", title="Calculus"),
            ]
        )
        db.flush()
        db.execute(
            text(
                "INSERT INTO prereqs (parent_id,child_id,kind,confidence) VALUES ('a','b','strict',0.95)"
            )
        )
        db.commit()
    response = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [{"title": "Algebra", "week": 1}, {"title": "Calculus", "week": 2}]
        },
    )
    assert response.status_code == 201, response.text
    with app.state.database.sessions() as db:
        nodes = list(db.scalars(select(RoadmapNode)))
        assert {n.concept_id for n in nodes} == {"a", "b"}
        edge = db.scalars(select(RoadmapEdge)).one()
        assert (
            edge.kind == "strict" and edge.origin == "llm" and edge.confidence == 0.95
        )


def test_deleting_user_cascades_private_graph_but_preserves_shared_resources(
    app, client, headers, roadmap, clock
):
    from sqlalchemy import delete

    from assistant.backend.catalog_models import GraphLayout

    node = roadmap["nodes"][0]["id"]
    path = f"/api/v1/roadmaps/{roadmap['id']}/layout"
    assert (
        client.put(
            path,
            headers=headers,
            json={"positions": [{"node_id": node, "x": 1, "y": 2}]},
        ).status_code
        == 200
    )
    with app.state.database.sessions() as db:
        add_resource(db, clock[0])
        db.execute(delete(User).where(User.id == roadmap["user_id"]))
        db.commit()
        assert db.scalar(select(func.count()).select_from(GraphLayout)) == 0
        assert db.scalar(select(func.count()).select_from(RoadmapEdge)) == 0
        assert db.scalar(select(func.count()).select_from(Resource)) == 1


def test_catalog_short_circuit_never_invokes_web_or_model(
    app, client, headers, roadmap, clock, monkeypatch
):
    from assistant.backend import resources

    node_id = roadmap["nodes"][0]["id"]

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "External search or model called despite sufficient catalog"
        )

    monkeypatch.setattr(resources, "make_llm", forbidden)
    monkeypatch.setattr(resources, "make_search", forbidden)
    with app.state.database.sessions() as db:
        for number in range(3):
            add_resource(db, clock[0], number=number)
        result = resources.search_resources(db, {"node_id": node_id}, clock[0])
        assert result["catalog_sufficient"] and result["cost_usd"] == 0
        assert result["shown"] == 3 and result["search_id"]


def test_subject_review_queue_requires_admin_and_excludes_private_nodes(
    app, client, headers, roadmap, clock
):
    from assistant.backend.catalog_models import ResourceSubject

    path = "/api/v1/admin/catalog/subject-review-queue"
    assert client.get(path, headers=headers).status_code == 403
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        row = db.get(ResourceSubject, (resource.id, "ct.ladder"))
        row.confidence = 0.4
        user = db.get(User, roadmap["user_id"])
        user.role = "admin"
        db.commit()
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert len(response.json()["labels"]) == 1
    assert "node_id" not in response.json()["labels"][0]


def test_canonical_urls_are_unique_and_exercise_origin_cannot_be_ai(
    app, client, headers, roadmap, clock
):
    from sqlalchemy.exc import IntegrityError

    from assistant.backend.catalog_models import Exercise

    with app.state.database.sessions() as db:
        first = add_resource(db, clock[0])
        db.commit()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                Resource(
                    url=first.url, title="Duplicate", canonical_url=first.canonical_url
                )
            )
            db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                Exercise(
                    origin="ai",
                    resource_id=first.id,
                    quote_hash="x",
                    source_hash="x",
                    type="short",
                    prompt="Invented",
                    license="CC0-1.0",
                )
            )
            db.flush()


def test_summary_40_nodes_uses_bounded_queries_without_writes(app, client, headers):
    from sqlalchemy import event

    course = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014"}
    ).json()["id"]
    roadmap = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [{"title": f"Solution ladder {i}", "week": 1} for i in range(40)]
        },
    ).json()
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(app.state.database.engine, "before_cursor_execute", record)
    try:
        response = client.get(
            f"/api/v1/roadmaps/{roadmap['id']}/sources:summary", headers=headers
        )
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert len(response.json()["nodes"]) == 40
    assert len(statements) <= 17  # one more per data kind, never one per node
    assert all(statement == "SELECT" for statement in statements)


@pytest.mark.parametrize(
    ("revision", "creates_tables"),
    [("0009_roadmap_graph", True), ("0010_quoted_exercises", True), ("0011_material_method", False)],
)
def test_new_migrations_compile_to_postgresql_types(revision, creates_tables):
    import importlib.util
    import io
    import re

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    spec = importlib.util.spec_from_file_location(
        revision, ROOT / "alembic/versions" / (revision + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert "ALTER TABLE" in sql and ("CREATE TABLE" in sql) == creates_tables
    assert not re.search(r"\bDATETIME\b|\bDOUBLE\b(?! PRECISION)", sql)


@pytest.mark.parametrize("status", ["pending", "rejected", "stale"])
def test_legacy_resource_api_cannot_bypass_verification(
    app, client, headers, roadmap, clock, status
):
    from assistant.backend.models import NodeResource

    node_id = roadmap["nodes"][0]["id"]
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0], status=status)
        db.add(
            NodeResource(node_id=node_id, resource_id=resource.id, relevance_score=0.95)
        )
        db.commit()
    response = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["resources"] == []
    assert response.json()["status"] == "insufficient"


def test_removed_source_can_recover_without_reintroducing_user_rejection(
    app, client, headers, roadmap, clock
):
    from assistant.backend.catalog_repository import refresh_node_sources
    from assistant.backend.models import NodeResource

    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        node = db.get(RoadmapNode, roadmap["nodes"][0]["id"])
        graph = db.get(Roadmap, roadmap["id"])
        course = db.get(Course, roadmap["course_id"])
        refresh_node_sources(db, [node], graph, course, clock[0])
        db.flush()
        link = db.get(NodeResource, (node.id, resource.id))
        assert link.status == "shown"
        resource.verification_status = "stale"
        db.flush()
        refresh_node_sources(db, [node], graph, course, clock[0])
        db.flush()
        assert link.status == "removed"
        resource.verification_status = "verified"
        db.flush()
        recovered = refresh_node_sources(db, [node], graph, course, clock[0])
        db.flush()
        assert any(r["id"] == resource.id for r in recovered[node.id]["sources"])
        assert link.status == "shown"
        link.status = "replaced"
        db.flush()
        rejected = refresh_node_sources(db, [node], graph, course, clock[0])
        db.flush()
        assert all(r["id"] != resource.id for r in rejected[node.id]["sources"])
        assert link.status == "replaced"


def test_catalog_license_change_hides_old_exercise_until_reimport(
    app, client, headers, roadmap, clock
):
    from assistant.backend.catalog_models import Exercise

    node_id = roadmap["nodes"][0]["id"]
    source_text = "Exercise 1: Solution ladder?"
    item = {"prompt": "Solution ladder?", "location": "Exercise 1"}
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        exercise = import_catalog_exercise(db, resource.id, source_text, item, clock[0])
        db.add(NodeExercise(node_id=node_id, exercise_id=exercise.id, role="practice"))
        db.commit()
        resource_id, exercise_id = resource.id, exercise.id
    endpoint = f"/api/v1/roadmap-nodes/{node_id}/exercises"
    assert (
        client.get(endpoint, headers=headers).json()["exercises"][0]["prompt"]
        == item["prompt"]
    )
    with app.state.database.sessions() as db:
        resource = db.get(Resource, resource_id)
        resource.license = "CC-BY-NC-SA-4.0"
        db.commit()
    assert client.get(endpoint, headers=headers).json()["count"] == 0
    with app.state.database.sessions() as db:
        refreshed = import_catalog_exercise(
            db, resource_id, source_text, item, clock[0]
        )
        db.commit()
        assert refreshed.id == exercise_id
        assert db.get(Exercise, exercise_id).prompt is None
    result = client.get(endpoint, headers=headers).json()["exercises"][0]
    assert (
        result["prompt"] is None
        and result["choices"] == []
        and not result["auto_grade"]
    )
    assert result["citation"]["license"] == "CC-BY-NC-SA-4.0"


def test_roadmap_edges_and_layouts_schema_invariants(app, roadmap):
    from sqlalchemy.exc import IntegrityError

    from assistant.backend.catalog_models import GraphLayout, RoadmapEdge
    from assistant.backend.roadmap_repository import CycleError, add_roadmap_edge

    first, second = roadmap["nodes"]
    roadmap_id = roadmap["id"]
    user_id = roadmap["user_id"]

    with app.state.database.sessions() as db:
        # 1. CHECK (parent_id <> child_id)
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                RoadmapEdge(
                    roadmap_id=roadmap_id,
                    parent_id=first["id"],
                    child_id=first["id"],
                    kind="strict",
                    origin="user",
                    confidence=1.0,
                    created_by=user_id,
                )
            )
            db.flush()

        # 2. CHECK confidence BETWEEN 0 AND 1
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                RoadmapEdge(
                    roadmap_id=roadmap_id,
                    parent_id=first["id"],
                    child_id=second["id"],
                    kind="strict",
                    origin="user",
                    confidence=1.5,
                    created_by=user_id,
                )
            )
            db.flush()

        # 3. Add valid edge via add_roadmap_edge
        edge = add_roadmap_edge(
            db,
            roadmap_id,
            parent_id=first["id"],
            child_id=second["id"],
            kind="strict",
            created_by=user_id,
        )
        db.commit()
        assert edge.parent_id == first["id"]
        assert edge.child_id == second["id"]

        # 4. Cycle rejection with exact path
        with pytest.raises(CycleError) as exc_info:
            add_roadmap_edge(
                db,
                roadmap_id,
                parent_id=second["id"],
                child_id=first["id"],
                kind="strict",
                created_by=user_id,
            )
        assert exc_info.value.path == [second["id"], first["id"], second["id"]]

        # 5. GraphLayout creation and cascade on node deletion
        db.add(
            GraphLayout(
                user_id=user_id,
                node_id=first["id"],
                x=100.0,
                y=200.0,
                pinned=True,
            )
        )
        db.commit()
        assert db.scalar(select(func.count()).select_from(GraphLayout)) == 1

        # Delete first node and check cascade
        node_obj = db.get(RoadmapNode, first["id"])
        db.delete(node_obj)
        db.commit()

        # Both GraphLayout and RoadmapEdge referencing first node should be cascaded
        assert db.scalar(select(func.count()).select_from(GraphLayout)) == 0
        assert db.scalar(select(func.count()).select_from(RoadmapEdge)) == 0

