"""Batch query-count and parity tests for catalog_repository (#102)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import event

from assistant.backend import catalog_repository
from assistant.backend.catalog_models import NodeSourceStatus
from assistant.backend.models import (
    Course,
    NodeResource,
    Resource,
    Roadmap,
    RoadmapNode,
    User,
)


def _seed_roadmap_with_nodes(db, count: int, email_prefix: str):
    uid = str(uuid4())
    cid = str(uuid4())
    rid = str(uuid4())
    db.add(
        User(
            id=uid,
            email=f"{email_prefix}-{uid[:6]}@example.com",
            password_hash="test-hash",
            name="Tester",
        )
    )
    db.flush()
    course = Course(
        id=cid, owner_id=uid, title=f"Course {email_prefix}", language="en", level="university"
    )
    db.add(course)
    db.flush()
    roadmap = Roadmap(id=rid, course_id=cid, user_id=uid, title="Map")
    db.add(roadmap)
    db.flush()
    nodes = [
        RoadmapNode(
            id=str(uuid4()),
            roadmap_id=rid,
            title=f"Topic {i}",
            type="topic",
            week=1 + (i // 3),
        )
        for i in range(count)
    ]
    db.add_all(nodes)
    db.flush()
    return course, roadmap, nodes


def _seed_resources(db, count: int):
    resources = [
        Resource(
            id=str(uuid4()),
            url=f"https://example.edu/r/{uuid4().hex}",
            canonical_url=f"https://example.edu/r/{i}-{uuid4().hex}",
            title=f"Resource {i}",
            verification_status="verified",
        )
        for i in range(count)
    ]
    db.add_all(resources)
    db.flush()
    return resources


def test_save_node_sources_batches_status_and_node_resource_queries(
    app, client, monkeypatch
):
    """save_node_sources updates statuses and links in O(1) SELECTs regardless of node count."""
    now = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    with app.state.database.sessions() as db:
        course, roadmap, nodes = _seed_roadmap_with_nodes(db, 12, "savebatch")
        resources = _seed_resources(db, 3)

        # Pre-seed node 0 with an existing status, a previously removed link (re-selected),
        # and a previously shown stale link (must flip to removed).
        db.add(NodeSourceStatus(node_id=nodes[0].id, status="insufficient", updated_at=now))
        db.add(
            NodeResource(
                node_id=nodes[0].id,
                resource_id=resources[0].id,
                status="removed",
                relevance_score=0.2,
            )
        )
        db.add(
            NodeResource(
                node_id=nodes[0].id,
                resource_id=resources[2].id,
                status="shown",
                relevance_score=0.4,
            )
        )
        db.commit()

        fake_result = {
            node.id: {
                "status": "sufficient",
                "sources": [
                    {"id": resources[0].id, "kind": "article", "score": 0.91},
                    {"id": resources[1].id, "kind": "video", "score": 0.85},
                    {"id": "private-1", "kind": "user_material", "score": 1.0},
                ],
            }
            for node in nodes
        }
        monkeypatch.setattr(
            catalog_repository,
            "node_sources",
            lambda db, nodes, roadmap, course, now, *, catalog=None: fake_result,
        )

        queries: list[str] = []

        def _track(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            catalog_repository.save_node_sources(db, nodes, roadmap, course, now)
            db.flush()
        finally:
            event.remove(engine, "before_cursor_execute", _track)

        select_queries = [q for q in queries if q.lstrip().upper().startswith("SELECT")]
        # Only 2 SELECTs total (NodeSourceStatus IN + NodeResource IN), not 4 * 12 = 48
        assert len(select_queries) == 2

        link_0_0 = db.get(NodeResource, (nodes[0].id, resources[0].id))
        link_0_1 = db.get(NodeResource, (nodes[0].id, resources[1].id))
        link_0_2 = db.get(NodeResource, (nodes[0].id, resources[2].id))
        assert link_0_0.status == "shown"
        assert link_0_0.relevance_score == 0.91
        assert link_0_1.status == "shown"
        assert link_0_2.status == "removed"
        assert db.get(NodeSourceStatus, nodes[0].id).status == "sufficient"
        assert db.get(NodeSourceStatus, nodes[-1].id).status == "sufficient"


def test_rematch_insufficient_batches_roadmap_and_course_lookups(
    app, client, monkeypatch
):
    """rematch_insufficient prefetches roadmaps and courses in bulk and skips catalog when empty."""
    now = datetime(2026, 11, 13, 11, 0, tzinfo=UTC)
    with app.state.database.sessions() as db:
        # Empty queue: must not scan verified resources
        ver_calls = []
        monkeypatch.setattr(
            catalog_repository,
            "verified_resources",
            lambda db, now: ver_calls.append(1) or [],
        )
        assert catalog_repository.rematch_insufficient(db, now) == {
            "insufficient_before": 0,
            "insufficient_after": 0,
        }
        assert ver_calls == []

        # Create 4 independent roadmaps/courses with insufficient nodes
        pairs = [_seed_roadmap_with_nodes(db, 1, f"rematch{i}") for i in range(4)]
        for _, _, nodes in pairs:
            db.add(NodeSourceStatus(node_id=nodes[0].id, status="insufficient", updated_at=now))
        db.commit()

        monkeypatch.setattr(
            catalog_repository,
            "node_sources",
            lambda db, nodes, roadmap, course, now, *, catalog=None: {
                n.id: {"status": "sufficient", "sources": []} for n in nodes
            },
        )

        queries: list[str] = []

        def _track(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            summary = catalog_repository.rematch_insufficient(db, now)
        finally:
            event.remove(engine, "before_cursor_execute", _track)

        assert summary == {"insufficient_before": 4, "insufficient_after": 0}
        roadmap_selects = [q for q in queries if "FROM roadmaps" in q and "roadmap_nodes" not in q]
        course_selects = [q for q in queries if "FROM courses" in q]
        assert len(roadmap_selects) == 1
        assert len(course_selects) == 1
