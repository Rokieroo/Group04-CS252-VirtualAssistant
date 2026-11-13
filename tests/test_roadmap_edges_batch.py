"""Batching and course-scoped prereq query tests for roadmap_repository (#100)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event, select, text

from app.roadmap.graph import Edge
from assistant.backend.catalog_models import RoadmapEdge
from assistant.backend.models import Course, Roadmap, RoadmapNode, User
from assistant.backend.roadmap_repository import (
    CycleError,
    persist_built_edges,
    persist_generated_edges,
)


def _seed_user_course_roadmap(db, email_prefix: str, title: str):
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
    db.add(Course(id=cid, owner_id=uid, title=title, language="en", level="university"))
    db.flush()
    roadmap = Roadmap(id=rid, course_id=cid, user_id=uid, title=f"{title} Map")
    db.add(roadmap)
    db.flush()
    return uid, cid, roadmap


def test_persist_generated_edges_batches_queries_and_filters_prereqs_by_course(app, client):
    """Generating edges across many weeks runs O(1) queries and scopes prereqs to the course."""
    with app.state.database.sessions() as db:
        _, course_a, roadmap_a = _seed_user_course_roadmap(db, "batcha", "Algorithms")
        _, course_b, _ = _seed_user_course_roadmap(db, "batchb", "Physics")

        # Create 6 weeks x 3 nodes = 18 nodes -> 5 * 3 * 3 = 45 week_order edges.
        nodes_a: list[RoadmapNode] = []
        for week in range(1, 7):
            for idx in range(3):
                node = RoadmapNode(
                    id=str(uuid4()),
                    roadmap_id=roadmap_a.id,
                    title=f"Week {week} Topic {idx}",
                    type="topic",
                    week=week,
                )
                db.add(node)
                nodes_a.append(node)

        # Concepts + prereq in course A (reverses Week 2 Topic 0 -> Week 1 Topic 0 to test precedence/skip)
        c1, c2 = str(uuid4()), str(uuid4())
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'w2t0', 'Week 2 Topic 0', '[1]')"
            ),
            {"id": c1, "cid": course_a},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'w1t0', 'Week 1 Topic 0', '[1]')"
            ),
            {"id": c2, "cid": course_a},
        )
        db.execute(
            text(
                "INSERT INTO prereqs (parent_id, child_id, kind, confidence) "
                "VALUES (:p, :c, 'strict', 0.9)"
            ),
            {"p": c1, "c": c2},
        )

        # Unrelated prereq in course B must not break or slow course A
        cb1, cb2 = str(uuid4()), str(uuid4())
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'phy1', 'Week 1 Topic 0', '[1]')"
            ),
            {"id": cb1, "cid": course_b},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'phy2', 'Week 2 Topic 0', '[1]')"
            ),
            {"id": cb2, "cid": course_b},
        )
        db.execute(
            text(
                "INSERT INTO prereqs (parent_id, child_id, kind, confidence) "
                "VALUES (:p, :c, 'strict', 1.0)"
            ),
            {"p": cb1, "c": cb2},
        )
        db.commit()

        executed_sql: list[str] = []

        def _count_sql(conn, cursor, statement, parameters, context, executemany):
            executed_sql.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _count_sql)
        try:
            persist_generated_edges(db, roadmap_a, nodes_a)
            db.commit()
        finally:
            event.remove(engine, "before_cursor_execute", _count_sql)

        # Count DB roundtrips: bounded O(1), far fewer than 46 edges
        assert len(executed_sql) <= 12
        prereq_queries = [s for s in executed_sql if "prereqs" in s.lower()]
        assert len(prereq_queries) == 1
        assert "course_id" in prereq_queries[0].lower()

        edges = list(
            db.scalars(
                select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap_a.id)
            )
        )
        # 1 strict llm edge + (45 - 1 cyclic opposite week_order edge) = 45 edges
        assert len(edges) == 45
        by_pair = {(e.parent_id, e.child_id): e for e in edges}
        w2_t0 = next(n.id for n in nodes_a if n.title == "Week 2 Topic 0")
        w1_t0 = next(n.id for n in nodes_a if n.title == "Week 1 Topic 0")
        assert (w2_t0, w1_t0) in by_pair
        assert by_pair[(w2_t0, w1_t0)].origin == "llm"
        assert by_pair[(w2_t0, w1_t0)].kind == "strict"
        assert (w1_t0, w2_t0) not in by_pair  # skipped because it would create cycle


def test_persist_generated_edges_aborts_on_strict_cycle_and_persist_built_edges_batches(app, client):
    """Strict prereq cycles still raise CycleError without partial inserts, and built edges batch cleanly."""
    with app.state.database.sessions() as db:
        _, course_id, roadmap = _seed_user_course_roadmap(db, "cycles", "Graphs")
        n1 = RoadmapNode(
            id=str(uuid4()), roadmap_id=roadmap.id, title="Topic A", type="topic", week=1
        )
        n2 = RoadmapNode(
            id=str(uuid4()), roadmap_id=roadmap.id, title="Topic B", type="topic", week=2
        )
        db.add_all([n1, n2])
        db.flush()

        # Test persist_built_edges batching first
        built = [
            Edge(
                parent=n1.id,
                child=n2.id,
                kind="soft",
                confidence=0.8,
                reason="r" * 350,
            )
        ]
        persist_built_edges(db, roadmap.id, built)
        stored = list(
            db.scalars(select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap.id))
        )
        assert len(stored) == 1
        assert stored[0].origin == "week_order"
        assert len(stored[0].reason) == 300

        # Trying to build an inverse edge raises CycleError cleanly without inserting
        with pytest.raises(CycleError):
            persist_built_edges(
                db,
                roadmap.id,
                [Edge(parent=n2.id, child=n1.id, kind="strict", confidence=1.0, reason="loop")],
            )
        stored_after = list(
            db.scalars(select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap.id))
        )
        assert len(stored_after) == 1

        # Clean edges and verify strict prereq cycle abort
        db.execute(
            text("DELETE FROM roadmap_edges WHERE roadmap_id = :rid"),
            {"rid": roadmap.id},
        )
        ca, cb = str(uuid4()), str(uuid4())
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'a', 'Topic A', '[1]')"
            ),
            {"id": ca, "cid": course_id},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                "VALUES (:id, :cid, 'b', 'Topic B', '[2]')"
            ),
            {"id": cb, "cid": course_id},
        )
        db.execute(
            text(
                "INSERT INTO prereqs (parent_id, child_id, kind, confidence) VALUES (:p, :c, 'strict', 1.0)"
            ),
            {"p": ca, "c": cb},
        )
        db.execute(
            text(
                "INSERT INTO prereqs (parent_id, child_id, kind, confidence) VALUES (:p, :c, 'strict', 1.0)"
            ),
            {"p": cb, "c": ca},
        )
        db.flush()

        with pytest.raises(CycleError):
            persist_generated_edges(db, roadmap, [n1, n2])
        assert (
            list(
                db.scalars(
                    select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap.id)
                )
            )
            == []
        )
