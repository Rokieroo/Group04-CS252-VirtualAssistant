"""All persisted graph writes pass the same transaction boundary (#100).

The no-op UPDATE acquires a row lock on PostgreSQL and the writer lock on SQLite
before reading edges. Unlike a process mutex, it also serializes other workers.
The caller must commit or roll back before handing the connection back.
"""

import math
from dataclasses import dataclass
from itertools import pairwise

from sqlalchemy import select, text, update

from app.concepts import comparison_key
from app.roadmap.graph import would_create_cycle_adjacency
from app.roadmap.nodes import prerequisites

from .catalog_models import Concept, GraphLayout, RoadmapEdge
from .models import Course, Roadmap, RoadmapNode, utcnow


class CycleError(ValueError):
    def __init__(self, path):
        self.path = path
        super().__init__("dependency_cycle")


@dataclass(frozen=True, slots=True)
class _EdgeSpec:
    parent_id: str
    child_id: str
    kind: str = "strict"
    origin: str = "user"
    confidence: float = 1.0
    reason: str = ""
    created_by: str | None = None
    skip_cycle: bool = False


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


def _validate_edge_spec(spec: _EdgeSpec) -> None:
    if spec.kind not in {"strict", "soft"} or spec.origin not in {
        "user",
        "llm",
        "week_order",
    }:
        raise ValueError("invalid_edge_kind_or_origin")
    if (
        not math.isfinite(spec.confidence)
        or not 0 <= spec.confidence <= 1
        or len(spec.reason) > 300
    ):
        raise ValueError("invalid_edge_metadata")


def _add_roadmap_edges(
    db, roadmap_id: str, specs: list[_EdgeSpec]
) -> list[RoadmapEdge]:
    """Validate and persist a batch of edges under a single roadmap write lock (#100)."""
    for spec in specs:
        _validate_edge_spec(spec)
    if not specs:
        return []

    result = db.execute(
        update(Roadmap).where(Roadmap.id == roadmap_id).values(title=Roadmap.title)
    )
    if result.rowcount != 1:
        raise LookupError("Roadmap not found")

    nodes = list(
        db.scalars(select(RoadmapNode).where(RoadmapNode.roadmap_id == roadmap_id))
    )
    node_ids = {n.id for n in nodes}
    for spec in specs:
        if spec.parent_id not in node_ids or spec.child_id not in node_ids:
            raise ValueError("edge_crosses_roadmap")

    existing_edges = list(
        db.scalars(
            select(RoadmapEdge)
            .where(RoadmapEdge.roadmap_id == roadmap_id)
            .execution_options(populate_existing=True)
        )
    )
    existing_by_pair: dict[tuple[str, str], RoadmapEdge] = {
        (edge.parent_id, edge.child_id): edge for edge in existing_edges
    }

    # Build adjacency once: persisted edges + milestone coverage links from GET .../graph.
    adjacency: dict[str, list[str]] = {}
    for parent_id, child_id in existing_by_pair:
        adjacency.setdefault(parent_id, []).append(child_id)
    for milestone_id, topic_ids in prerequisites(nodes).items():
        for topic_id in topic_ids:
            adjacency.setdefault(topic_id, []).append(milestone_id)

    persisted: list[RoadmapEdge] = []
    new_edges: list[RoadmapEdge] = []
    for spec in specs:
        pair = (spec.parent_id, spec.child_id)
        existing = existing_by_pair.get(pair)
        if existing is not None:
            persisted.append(existing)
            continue

        path = would_create_cycle_adjacency(adjacency, spec.parent_id, spec.child_id)
        if path:
            if spec.skip_cycle:
                continue
            raise CycleError(path)

        edge = RoadmapEdge(
            roadmap_id=roadmap_id,
            parent_id=spec.parent_id,
            child_id=spec.child_id,
            kind=spec.kind,
            origin=spec.origin,
            confidence=spec.confidence,
            reason=spec.reason,
            created_by=spec.created_by,
        )
        existing_by_pair[pair] = edge
        adjacency.setdefault(spec.parent_id, []).append(spec.child_id)
        new_edges.append(edge)
        persisted.append(edge)

    if new_edges:
        db.add_all(new_edges)
        db.flush()
    return persisted


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
    return _add_roadmap_edges(
        db,
        roadmap_id,
        [
            _EdgeSpec(
                parent_id=parent_id,
                child_id=child_id,
                kind=kind,
                origin=origin,
                confidence=confidence,
                reason=reason,
                created_by=created_by,
            )
        ],
    )[0]


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

    specs: list[_EdgeSpec] = []
    if by_concept:
        rows = db.execute(
            text(
                "SELECT p.parent_id, p.child_id, p.kind, p.confidence "
                "FROM prereqs p "
                "JOIN concepts c ON c.id = p.parent_id "
                "WHERE c.course_id = :course_id"
            ),
            {"course_id": roadmap.course_id},
        )
        for row in rows:
            if row.parent_id in by_concept and row.child_id in by_concept:
                specs.append(
                    _EdgeSpec(
                        parent_id=by_concept[row.parent_id],
                        child_id=by_concept[row.child_id],
                        kind=row.kind,
                        origin="llm",
                        confidence=row.confidence,
                        created_by=roadmap.user_id,
                        skip_cycle=False,
                    )
                )

    weeks: dict[int, list[str]] = {}
    for node in sorted(nodes, key=lambda n: (n.week or 0, n.id)):
        if node.type == "topic" and node.week:
            weeks.setdefault(node.week, []).append(node.id)
    for before, after in pairwise(sorted(weeks)):
        for parent in weeks[before]:
            for child in weeks[after]:
                specs.append(
                    _EdgeSpec(
                        parent_id=parent,
                        child_id=child,
                        kind="soft",
                        origin="week_order",
                        created_by=roadmap.user_id,
                        skip_cycle=True,
                    )
                )

    _add_roadmap_edges(db, roadmap.id, specs)


def persist_built_edges(db, roadmap_id, edges, *, created_by=None):
    """Adapter for app.roadmap.builder output; never bypasses cycle validation."""
    specs = [
        _EdgeSpec(
            parent_id=edge.parent,
            child_id=edge.child,
            kind=edge.kind,
            origin="week_order" if edge.kind == "soft" else "llm",
            confidence=edge.confidence,
            reason=edge.reason[:300],
            created_by=created_by,
            skip_cycle=False,
        )
        for edge in edges
    ]
    _add_roadmap_edges(db, roadmap_id, specs)


def save_layouts(db, user_id, roadmap_id, positions):
    """Upsert one user's node positions on one roadmap in two queries (#103).

    ``positions`` are dicts with node_id, x, y, pinned; the last one per node wins.
    Raises LookupError with the first node id that is not on the roadmap.
    """
    latest = {p["node_id"]: p for p in positions}
    if not latest:
        return
    if not all(
        math.isfinite(v) and abs(v) <= 1e7 for p in latest.values() for v in (p["x"], p["y"])
    ):
        raise ValueError("invalid_coordinates")
    on_roadmap = set(
        db.scalars(
            select(RoadmapNode.id).where(
                RoadmapNode.roadmap_id == roadmap_id, RoadmapNode.id.in_(latest)
            )
        )
    )
    if missing := [node_id for node_id in latest if node_id not in on_roadmap]:
        raise LookupError(missing[0])
    existing = {
        row.node_id: row
        for row in db.scalars(
            select(GraphLayout).where(
                GraphLayout.user_id == user_id, GraphLayout.node_id.in_(latest)
            )
        )
    }
    now = utcnow()
    for node_id, p in latest.items():
        row = existing.get(node_id)
        if row is None:
            row = GraphLayout(user_id=user_id, node_id=node_id)
            db.add(row)
        row.x, row.y, row.pinned, row.updated_at = p["x"], p["y"], p["pinned"], now
