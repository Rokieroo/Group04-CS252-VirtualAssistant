"""All persisted graph writes pass the same transaction boundary (#100).

The no-op UPDATE acquires a row lock on PostgreSQL and the writer lock on SQLite
before reading edges. Unlike a process mutex, it also serializes other workers.
The caller must commit or roll back before handing the connection back.
"""

import math
from itertools import pairwise

from sqlalchemy import select, text, update

from app.concepts import comparison_key
from app.roadmap.graph import would_create_cycle
from app.roadmap.nodes import prerequisites

from .catalog_models import Concept, GraphLayout, RoadmapEdge
from .models import Course, Roadmap, RoadmapNode, utcnow


class CycleError(ValueError):
    def __init__(self, path):
        self.path = path
        super().__init__("dependency_cycle")


def owned_node(db, node_id, user_id):
    node = db.get(RoadmapNode, node_id)
    roadmap = node and db.get(Roadmap, node.roadmap_id)
    course = roadmap and db.get(Course, roadmap.course_id)
    if (
        not node
        or not roadmap
        or roadmap.user_id != user_id
        or not course
        or course.owner_id != user_id
    ):
        raise LookupError("Node not found")
    return node, roadmap, course


def add_roadmap_edge(
    db,
    roadmap_id,
    parent_id,
    child_id,
    *,
    kind="strict",
    origin="user",
    confidence=1.0,
    reason="",
    created_by=None,
):
    if kind not in {"strict", "soft"} or origin not in {"user", "llm", "week_order"}:
        raise ValueError("invalid_edge_kind_or_origin")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1 or len(reason) > 300:
        raise ValueError("invalid_edge_metadata")
    result = db.execute(
        update(Roadmap).where(Roadmap.id == roadmap_id).values(title=Roadmap.title)
    )
    if result.rowcount != 1:
        raise LookupError("Roadmap not found")
    endpoints = set(
        db.scalars(
            select(RoadmapNode.id).where(
                RoadmapNode.roadmap_id == roadmap_id,
                RoadmapNode.id.in_({parent_id, child_id}),
            )
        )
    )
    if endpoints != {parent_id, child_id}:
        raise ValueError("edge_crosses_roadmap")
    existing = db.get(RoadmapEdge, (parent_id, child_id), populate_existing=True)
    if existing:
        return existing  # idempotent; do not overwrite provenance on retries
    edges = db.execute(
        select(RoadmapEdge.parent_id, RoadmapEdge.child_id).where(
            RoadmapEdge.roadmap_id == roadmap_id
        )
    ).all()
    # The graph also shows each milestone after the topics it covers (GET .../graph);
    # an edge from a milestone back to one of those topics would close a visible cycle.
    covers = [
        (topic_id, milestone_id)
        for milestone_id, topic_ids in prerequisites(
            list(db.scalars(select(RoadmapNode).where(RoadmapNode.roadmap_id == roadmap_id)))
        ).items()
        for topic_id in topic_ids
    ]
    path = would_create_cycle(
        [tuple(edge) for edge in edges] + covers, parent_id, child_id
    )
    if path:
        raise CycleError(path)
    edge = RoadmapEdge(
        roadmap_id=roadmap_id,
        parent_id=parent_id,
        child_id=child_id,
        kind=kind,
        origin=origin,
        confidence=confidence,
        reason=reason,
        created_by=created_by,
    )
    db.add(edge)
    db.flush()
    return edge


def persist_generated_edges(db, roadmap, nodes):
    """Link existing course concepts and store strict prerequisites + week order.

    Strict edges take precedence. Inconsistent optional week edges are skipped;
    strict cycles abort the transaction instead of persisting a broken graph.
    """
    concepts = {
        comparison_key(c.title): c
        for c in db.scalars(
            select(Concept).where(Concept.course_id == roadmap.course_id)
        )
    }
    by_concept = {}
    for node in nodes:
        concept = concepts.get(comparison_key(node.title))
        if concept:
            node.concept_id = concept.id
            by_concept[concept.id] = node.id
    db.flush()
    for row in db.execute(
        text("SELECT parent_id, child_id, kind, confidence FROM prereqs")
    ):
        if row.parent_id in by_concept and row.child_id in by_concept:
            add_roadmap_edge(
                db,
                roadmap.id,
                by_concept[row.parent_id],
                by_concept[row.child_id],
                kind=row.kind,
                origin="llm",
                confidence=row.confidence,
                created_by=roadmap.user_id,
            )
    weeks = {}
    for node in sorted(nodes, key=lambda n: (n.week or 0, n.id)):
        if node.type == "topic" and node.week:
            weeks.setdefault(node.week, []).append(node.id)
    for before, after in pairwise(sorted(weeks)):
        for parent in weeks[before]:
            for child in weeks[after]:
                try:
                    add_roadmap_edge(
                        db,
                        roadmap.id,
                        parent,
                        child,
                        kind="soft",
                        origin="week_order",
                        created_by=roadmap.user_id,
                    )
                except CycleError:
                    continue


def persist_built_edges(db, roadmap_id, edges, *, created_by=None):
    """Adapter for app.roadmap.builder output; never bypasses cycle validation."""
    for edge in edges:
        add_roadmap_edge(
            db,
            roadmap_id,
            edge.parent,
            edge.child,
            kind=edge.kind,
            origin="week_order" if edge.kind == "soft" else "llm",
            confidence=edge.confidence,
            reason=edge.reason[:300],
            created_by=created_by,
        )


def save_layout(db, user_id, node_id, x, y, pinned=False):
    owned_node(db, node_id, user_id)
    if not all(math.isfinite(v) and abs(v) <= 1e7 for v in (x, y)):
        raise ValueError("invalid_coordinates")
    row = db.get(GraphLayout, (user_id, node_id))
    if row is None:
        row = GraphLayout(user_id=user_id, node_id=node_id, x=x, y=y, pinned=pinned)
        db.add(row)
    row.x, row.y, row.pinned, row.updated_at = x, y, pinned, utcnow()
    return row
