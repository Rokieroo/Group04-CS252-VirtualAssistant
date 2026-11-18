"""Tests for scoped verified resource checks and cached catalog decoding (#102, #168)."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

from conftest import register
from sqlalchemy import event

from app.catalog.taxonomy import ensure_taxonomy, subjects
from assistant.backend.catalog_models import (
    CatalogEmbedding,
    ResourceSubject,
)
from assistant.backend.catalog_repository import (
    node_sources,
    verified_resource_map,
    verified_resources,
)
from assistant.backend.models import (
    Course,
    NodeResource,
    PersonalSource,
    Resource,
    ResourceVerification,
    Roadmap,
    RoadmapNode,
)


def test_resources_and_library_skip_catalog_embeddings_and_enforce_read_gates(
    app, client, clock
):
    """Scoped resource checks avoid full-catalog/embedding scans while keeping verification gates."""
    now = clock[0]
    reg = register(client, email="res_fast@example.com")
    headers = {"Authorization": f"Bearer {reg['access_token']}"}
    user_id = reg["user"]["id"]

    with app.state.database.sessions() as db:
        course = Course(owner_id=user_id, title="CS252", language="en", level="university")
        db.add(course)
        db.flush()
        roadmap = Roadmap(course_id=course.id, user_id=user_id, title="CS252 Map")
        db.add(roadmap)
        db.flush()
        node = RoadmapNode(
            roadmap_id=roadmap.id, title="Balanced Trees", type="topic", week=1
        )
        db.add(node)
        db.flush()

        res_ok = Resource(
            id=str(uuid4()),
            url="https://ocw.mit.edu/trees",
            canonical_url="https://ocw.mit.edu/trees",
            title="Balanced Trees Lecture",
            provider="mit_ocw",
            kind="article",
            format="reading",
            lang="en",
            license="CC-BY-4.0",
            content_hash="abc123",
            http_status=200,
            verification_status="verified",
        )
        res_stale = Resource(
            id=str(uuid4()),
            url="https://ocw.mit.edu/stale",
            canonical_url="https://ocw.mit.edu/stale",
            title="Stale Resource",
            provider="mit_ocw",
            kind="article",
            format="reading",
            lang="en",
            license="CC-BY-4.0",
            content_hash="def456",
            http_status=200,
            verification_status="verified",
        )
        db.add_all([res_ok, res_stale])
        db.flush()

        for check_name in ("fetch", "domain", "license", "metadata"):
            db.add(
                ResourceVerification(
                    resource_id=res_ok.id,
                    check_name=check_name,
                    result="pass",
                    checked_by="auto",
                    checked_at=now,
                )
            )
            db.add(
                ResourceVerification(
                    resource_id=res_stale.id,
                    check_name=check_name,
                    result="pass",
                    checked_by="auto",
                    checked_at=now - timedelta(days=90),
                )
            )

        db.add_all(
            [
                NodeResource(node_id=node.id, resource_id=res_ok.id, relevance_score=0.9),
                NodeResource(node_id=node.id, resource_id=res_stale.id, relevance_score=0.8),
                PersonalSource(
                    node_id=node.id,
                    source_key=res_ok.id,
                    title=res_ok.title,
                    state="pinned",
                    note="",
                ),
                CatalogEmbedding(
                    id=res_ok.id,
                    kind="resource",
                    model="sha256-word-bigram-256-v1",
                    content_hash="abc123",
                    vector=json.dumps([0.1] * 8),
                    resource_id=res_ok.id,
                ),
            ]
        )
        db.commit()
        node_id = node.id
        res_ok_id = res_ok.id
        res_stale_id = res_stale.id

    with app.state.database.sessions() as db:
        scoped = verified_resource_map(db, now, [res_ok_id, res_stale_id])
        assert scoped == {res_ok_id: "https://ocw.mit.edu/trees"}

    queries: list[str] = []

    def _track(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", _track)
    try:
        res_resp = client.get(f"/api/v1/roadmap-nodes/{node_id}/resources", headers=headers)
        lib_resp = client.get("/api/v1/me/library", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", _track)

    assert res_resp.status_code == 200
    assert [r["id"] for r in res_resp.json()["resources"]] == [res_ok_id]
    assert lib_resp.status_code == 200
    assert lib_resp.json()[0]["url"] == "https://ocw.mit.edu/trees"
    assert not any("catalog_embeddings" in q.lower() for q in queries)
    assert not any("institutions" in q.lower() for q in queries)
    assert res_stale_id not in {r["id"] for r in res_resp.json()["resources"]}


def test_verified_resources_decodes_each_vector_once_until_it_changes(
    app, client, clock
):
    """Vectors are decoded once per worker and re-read when their text changes."""
    now = clock[0]
    with app.state.database.sessions() as db:
        ensure_taxonomy(db)
        res_verified = Resource(
            id=str(uuid4()),
            url="https://openstax.org/books/calc",
            canonical_url="https://openstax.org/books/calc",
            title="Calculus",
            provider="openstax",
            kind="article",
            format="reading",
            lang="en",
            license="CC-BY-4.0",
            content_hash="h1",
            http_status=200,
            verification_status="verified",
        )
        res_rejected = Resource(
            id=str(uuid4()),
            url="https://example.org/rejected",
            canonical_url="https://example.org/rejected",
            title="Rejected",
            provider="web",
            kind="article",
            format="reading",
            lang="en",
            license="CC-BY-4.0",
            content_hash="h2",
            http_status=200,
            verification_status="rejected",
        )
        db.add_all([res_verified, res_rejected])
        db.flush()
        for check_name in ("fetch", "domain", "license", "metadata"):
            db.add(
                ResourceVerification(
                    resource_id=res_verified.id,
                    check_name=check_name,
                    result="pass",
                    checked_by="auto",
                    checked_at=now,
                )
            )
        vec = json.dumps([0.25] * 16)
        db.add_all(
            [
                CatalogEmbedding(
                    id=res_verified.id,
                    kind="resource",
                    model="sha256-word-bigram-256-v1",
                    content_hash="h1",
                    vector=vec,
                    resource_id=res_verified.id,
                ),
                CatalogEmbedding(
                    id=res_rejected.id,
                    kind="resource",
                    model="sha256-word-bigram-256-v1",
                    content_hash="h2",
                    vector=json.dumps([0.9] * 16),
                    resource_id=res_rejected.id,
                ),
                ResourceSubject(
                    resource_id=res_rejected.id,
                    subject_id=subjects()[0]["id"],
                    confidence=0.9,
                    method="rule:title",
                ),
            ]
        )
        db.commit()

        first = verified_resources(db, now)
        second = verified_resources(db, now)
        assert [r["id"] for r in first] == [res_verified.id]  # the rejected row never shows
        assert second[0]["vector"] is first[0]["vector"]  # decoded once, not per request

        # Re-embedding new text changes content_hash, so the new vector is read.
        row = db.get(CatalogEmbedding, (res_verified.id, "resource"))
        row.content_hash, row.vector = "h1-v2", json.dumps([0.5] * 16)
        db.commit()
        assert verified_resources(db, now)[0]["vector"].tolist() == [0.5] * 16

        assert node_sources(db, [], None, None, now) == {}
