"""Node learning sources, quoted exercises and graph write contracts."""

import json
import threading
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, update

from app.planner.fsrs import compute_node_mastery
from app.roadmap import layers, local_graph, prerequisites, transitive_reduction

from .catalog_models import Concept, GraphLayout, RoadmapEdge
from .catalog_repository import node_sources
from .dependencies import DB, CurrentUser
from .exercise_repository import exercises_for_node
from .material_repository import decide, node_materials
from .models import (
    Course,
    LearningOutcome,
    Notification,
    ReviewCard,
    Roadmap,
    RoadmapNode,
    Source,
    Task,
    utcnow,
)
from .roadmap_repository import CycleError, add_roadmap_edge, owned_node
from .routes_core import _latest_syllabus, _owned_roadmap
from .schemas import RoadmapGraphOut

router = APIRouter(tags=["Node learning and graph"])

EDGE_EDITS_PER_MINUTE = 120  # issue #103
_EDGE_EDIT_WINDOW_SECONDS = 60
_EDGE_EDIT_CACHE_CAP = 1024
# shortcut: counted per worker process, so N workers allow N x 120/min and a restart
# forgets; move to a shared store (an edge-edit log table or Redis) if edits get abused.
_edge_edits: dict[str, list[float]] = defaultdict(list)
_edge_edits_lock = threading.Lock()


def _check_edge_rate_limit(user_id: str, now_ts: float):
    cutoff = now_ts - _EDGE_EDIT_WINDOW_SECONDS
    with _edge_edits_lock:
        if len(_edge_edits) > _EDGE_EDIT_CACHE_CAP:
            stale_users = [
                uid
                for uid, timestamps in _edge_edits.items()
                if not any(t > cutoff for t in timestamps)
            ]
            for uid in stale_users:
                del _edge_edits[uid]
        recent = [t for t in _edge_edits.get(user_id, ()) if t > cutoff]
        if len(recent) >= EDGE_EDITS_PER_MINUTE:
            _edge_edits[user_id] = recent
            raise HTTPException(
                429, "Edge edit rate limit reached (120/min)", headers={"Retry-After": "60"}
            )
        _edge_edits[user_id] = [*recent, now_ts]


def _mark_replan_needed(db, user_id: str, roadmap_id: str) -> None:
    """Edge edits change what can be studied when: one unread nudge to replan (#65)."""
    message = f"Roadmap {roadmap_id} edges updated; schedule replan required."
    unread = db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.message == message,
            Notification.read.is_(False),
        )
    )
    if unread is None:
        db.add(Notification(user_id=user_id, message=message))


class RankedSourceOut(BaseModel):
    kind: Literal["user_material", "catalog", "web"]
    id: str
    title: str
    url: str | None = None
    source_id: str | None = None
    pages: list[int] = Field(default_factory=list)
    provider: str
    institution: str | None = None
    license: str
    format: str
    duration_min: int | None = None
    verification_status: str
    score: float
    reason: str


class NodeSourceSummary(BaseModel):
    node_id: str
    status: Literal["ready", "insufficient"]
    source_count: int
    user_material_count: int


class NodeSourcesOut(NodeSourceSummary):
    sources: list[RankedSourceOut]


class SourceSummaryOut(BaseModel):
    roadmap_id: str
    nodes: list[NodeSourceSummary]


class ExerciseCitationOut(BaseModel):
    source_id: str | None
    resource_id: str | None
    title: str
    page: int | None = None
    url: str | None
    institution: str | None
    license: str

    @model_validator(mode="after")
    def _cites_one_source(self):
        # Last line of defence (#115): no question leaves the API without its source.
        if (self.source_id is None) == (self.resource_id is None):
            raise ValueError("an exercise cites exactly one source_id or resource_id")
        return self


class ExerciseOut(BaseModel):
    id: str
    type: Literal["mcq", "numeric", "short", "proof", "code"]
    prompt: str | None
    choices: list[str]
    difficulty: int
    bloom_level: str
    auto_grade: bool
    location: str | None
    citation: ExerciseCitationOut


class ExercisesOut(BaseModel):
    node_id: str
    role: Literal["practice", "checkpoint"]
    status: Literal["ready", "insufficient"]
    required: int
    count: int
    exercises: list[ExerciseOut]


def _node(db, node_id, user_id):
    try:
        return owned_node(db, node_id, user_id)
    except LookupError:
        raise HTTPException(404, "Node not found") from None


@router.get("/concepts/{node_id}/sources", response_model=NodeSourcesOut)
def sources(
    node_id: str,
    db: DB,
    user: CurrentUser,
    request: Request,
    limit: int = Query(5, ge=1, le=5),
):
    node, roadmap, course = _node(db, node_id, user.id)
    return node_sources(
        db, [node], roadmap, course, request.app.state.now(), limit=limit
    )[node.id]


@router.get("/roadmaps/{roadmap_id}/sources:summary", response_model=SourceSummaryOut)
def summary(roadmap_id: str, db: DB, user: CurrentUser, request: Request):
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    nodes = list(
        db.scalars(select(RoadmapNode).where(RoadmapNode.roadmap_id == roadmap_id))
    )
    values = node_sources(
        db, nodes, roadmap, db.get(Course, roadmap.course_id), request.app.state.now()
    )
    return {
        "roadmap_id": roadmap_id,
        "nodes": [
            {k: v for k, v in value.items() if k != "sources"}
            for value in values.values()
        ],
    }


@router.get("/roadmap-nodes/{node_id}/exercises", response_model=ExercisesOut)
def exercises(
    node_id: str,
    db: DB,
    user: CurrentUser,
    request: Request,
    role: Literal["practice", "checkpoint"] = "practice",
    limit: int = Query(10, ge=1, le=50),
):
    node, roadmap, course = _node(db, node_id, user.id)
    return exercises_for_node(
        db, node, roadmap, course, request.app.state.now(), role=role, limit=limit
    )


class MaterialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attached: bool


class MaterialPageOut(BaseModel):
    source_id: str
    page: int
    confidence: float
    method: Literal["auto", "manual"]


class MaterialFileOut(BaseModel):
    file_name: str
    status: Literal["attached", "suggested"]
    pages: list[MaterialPageOut]


class NodeMaterialsOut(BaseModel):
    node_id: str
    files: list[MaterialFileOut]


def _course_page(db, course, source_id) -> Source:
    source = db.get(Source, source_id)
    if source is None or source.course_id != course.id:
        raise HTTPException(404, "Source not found")  # never reveal others' material
    return source


@router.get("/roadmap-nodes/{node_id}/materials", response_model=NodeMaterialsOut)
def list_materials(node_id: str, db: DB, user: CurrentUser):
    """The learner's own pages on this node: attached, then those awaiting one tap."""
    node, _, _ = _node(db, node_id, user.id)
    return {"node_id": node.id, "files": node_materials(db, node)}


@router.post("/roadmap-nodes/{node_id}/materials", status_code=201)
def attach_material(node_id: str, data: MaterialIn, db: DB, user: CurrentUser):
    node, _, course = _node(db, node_id, user.id)
    source = _course_page(db, course, data.source_id)
    decide(db, node, source, attached=True, owner_id=user.id)
    db.commit()
    return {"node_id": node_id, "source_id": source.id, "pages": [source.page]}


@router.put(
    "/roadmap-nodes/{node_id}/materials/{source_id}", response_model=MaterialPageOut
)
def decide_material(
    node_id: str, source_id: str, data: DecisionIn, db: DB, user: CurrentUser
):
    """One tap: confirm a suggested page for this node, or reject it for good."""
    node, _, course = _node(db, node_id, user.id)
    source = _course_page(db, course, source_id)
    row = decide(db, node, source, attached=data.attached, owner_id=user.id)
    db.commit()
    return {
        "source_id": source.id,
        "page": source.page,
        "confidence": row.confidence,
        "method": row.method,
    }


def _build_roadmap_graph(
    db: DB, roadmap_id: str, user_id: str, now: datetime, *, reduce: bool = False
) -> dict:
    roadmap = _owned_roadmap(db, roadmap_id, user_id)
    course = db.get(Course, roadmap.course_id)
    nodes = list(
        db.scalars(
            select(RoadmapNode)
            .where(RoadmapNode.roadmap_id == roadmap_id)
            .order_by(RoadmapNode.week, RoadmapNode.id)
        )
    )
    if not nodes:
        return {"nodes": [], "edges": []}

    node_ids = [n.id for n in nodes]
    tasks = {
        t.roadmap_node_id: t
        for t in db.scalars(
            select(Task).where(
                Task.owner_id == user_id,
                Task.roadmap_node_id.in_(node_ids),
            )
        )
    }

    concept_ids = [n.concept_id for n in nodes if n.concept_id]
    concepts = (
        {
            c.id: c
            for c in db.scalars(select(Concept).where(Concept.id.in_(concept_ids)))
        }
        if concept_ids
        else {}
    )

    syllabus = _latest_syllabus(db, course.id)
    # A topic node is titled after its outcome (routes_core.generate_roadmap), so match
    # the title exactly; a substring test would tie "CLO1" to "CLO10".
    outcome_by_title = (
        {
            (o.description or o.code): o.id
            for o in db.scalars(
                select(LearningOutcome).where(
                    LearningOutcome.syllabus_id == syllabus.id
                )
            )
        }
        if syllabus
        else {}
    )

    # One bulk read for every node, the same one GET sources:summary makes (#102).
    sources_by_node = node_sources(db, nodes, roadmap, course, now)

    # Plain dicts: the route's response_model validates them once (300 nodes and ~1.4k
    # edges validated twice took most of the p95 budget, issue #103).
    edges = [
        dict(row)
        for row in db.execute(
            select(
                RoadmapEdge.parent_id.label("parent"),
                RoadmapEdge.child_id.label("child"),
                RoadmapEdge.kind,
                RoadmapEdge.origin,
                RoadmapEdge.confidence,
                RoadmapEdge.reason,
            ).where(RoadmapEdge.roadmap_id == roadmap_id)
        ).mappings()
    ] + [
        {
            "parent": topic_id,
            "child": milestone_id,
            "kind": "covers",
            "origin": "milestone_covers",
            "confidence": 1.0,
            "reason": "Milestone covers topic",
        }
        for milestone_id, topic_ids in prerequisites(nodes).items()
        for topic_id in topic_ids
    ]
    layer_of = layers(nodes, edges)

    # Calculate mastery per node for the current user (issue #162, UC-11)
    cards = list(
        db.scalars(
            select(ReviewCard).where(
                ReviewCard.user_id == user_id,
                ReviewCard.node_id.in_(node_ids),
            )
        )
    )
    cards_by_node: dict[str, list[ReviewCard]] = {nid: [] for nid in node_ids}
    for c in cards:
        if c.node_id in cards_by_node:
            cards_by_node[c.node_id].append(c)

    mastery_by_node = {
        nid: compute_node_mastery(node_cards, now)
        for nid, node_cards in cards_by_node.items()
    }

    graph_nodes = []
    for node in nodes:
        concept = concepts.get(node.concept_id)
        task = tasks.get(node.id)
        summary = sources_by_node.get(node.id, {})
        outcome_id = outcome_by_title.get(node.title)
        graph_nodes.append(
            {
                "id": node.id,
                "type": node.type,
                "title": node.title,
                "week": node.week,
                "est_minutes": node.duration_minutes,
                "due_at": node.due_at,
                "outcome_ids": [outcome_id] if outcome_id else [],
                "source_pages": json.loads(concept.source_pages or "[]")
                if concept
                else [],
                "status": task.status if task else "pending",
                "source_count": summary.get("source_count", 0),
                "user_material_count": summary.get("user_material_count", 0),
                "sources_status": summary.get("status", "insufficient"),
                "layer": layer_of[node.id],
                "mastery": mastery_by_node.get(node.id, 0.0),
            }
        )

    return {
        "nodes": graph_nodes,
        "edges": transitive_reduction(nodes, edges) if reduce else edges,
    }


@router.get("/roadmaps/{roadmap_id}/graph", response_model=RoadmapGraphOut)
def get_roadmap_graph(
    roadmap_id: str,
    db: DB,
    user: CurrentUser,
    request: Request,
    reduce: bool = Query(False),
):
    """Retrieve full course roadmap graph (issue #103, spec 8, UC-03)."""
    return _build_roadmap_graph(
        db, roadmap_id, user.id, request.app.state.now(), reduce=reduce
    )


@router.get("/roadmap-nodes/{node_id}/graph", response_model=RoadmapGraphOut)
def get_node_subgraph(
    node_id: str,
    db: DB,
    user: CurrentUser,
    request: Request,
    depth: int = Query(2, ge=1, le=5),
    direction: Literal["ancestors", "descendants", "both"] = Query("both"),
):
    """Retrieve local subgraph centered on a roadmap node (issue #97, #103)."""
    _, roadmap, _ = _node(db, node_id, user.id)
    graph = _build_roadmap_graph(db, roadmap.id, user.id, request.app.state.now())
    kept, edges = local_graph(
        graph["nodes"], graph["edges"], node_id, depth=depth, direction=direction
    )
    kept = set(kept)
    return {"nodes": [n for n in graph["nodes"] if n["id"] in kept], "edges": edges}


class EdgeIn(BaseModel):
    """``parent``/``child`` as in spec 8; the older ``parent_id``/``child_id`` still parse."""

    model_config = ConfigDict(extra="forbid")
    parent_id: str = Field(validation_alias=AliasChoices("parent", "parent_id"))
    child_id: str = Field(validation_alias=AliasChoices("child", "child_id"))
    kind: Literal["soft", "strict"] = "strict"
    reason: str = Field("", max_length=300)


@router.get("/roadmaps/{roadmap_id}/edges")
def list_edges(roadmap_id: str, db: DB, user: CurrentUser):
    _owned_roadmap(db, roadmap_id, user.id)
    return [
        {
            "parent_id": e.parent_id,
            "child_id": e.child_id,
            "kind": e.kind,
            "origin": e.origin,
            "confidence": e.confidence,
            "reason": e.reason,
        }
        for e in db.scalars(
            select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap_id)
        )
    ]


EDGE_ERRORS = {
    409: {"description": "Dependency cycle detected"},
    429: {"description": "Rate limit exceeded"},
}


# The /edges and /layout paths predate the spec 8 /graph/... ones; ui/src/api/core.ts
# still calls them, so they stay as undocumented aliases.
@router.post(
    "/roadmaps/{roadmap_id}/graph/edges", status_code=201, responses=EDGE_ERRORS
)
@router.post("/roadmaps/{roadmap_id}/edges", status_code=201, include_in_schema=False)
def add_edge(
    roadmap_id: str, data: EdgeIn, request: Request, db: DB, user: CurrentUser
):
    """Add a prerequisite edge; one that would close a cycle is a 409 with its path."""
    _check_edge_rate_limit(user.id, request.app.state.now().timestamp())
    _owned_roadmap(db, roadmap_id, user.id)
    try:
        edge = add_roadmap_edge(db, roadmap_id, **data.model_dump(), created_by=user.id)
        _mark_replan_needed(db, user.id, roadmap_id)
        db.commit()
        return {
            "parent_id": edge.parent_id,
            "child_id": edge.child_id,
            "kind": edge.kind,
            "origin": edge.origin,
            "confidence": edge.confidence,
            "reason": edge.reason,
        }
    except CycleError as exc:
        db.rollback()
        raise HTTPException(409, {"error": "cycle", "path": exc.path}) from None
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None


@router.delete(
    "/roadmaps/{roadmap_id}/graph/edges/{parent_id}/{child_id}",
    status_code=204,
    responses={429: EDGE_ERRORS[429]},
)
@router.delete(
    "/roadmaps/{roadmap_id}/edges/{parent_id}/{child_id}",
    status_code=204,
    include_in_schema=False,
)
def remove_edge(
    roadmap_id: str,
    parent_id: str,
    child_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    _check_edge_rate_limit(user.id, request.app.state.now().timestamp())
    _owned_roadmap(db, roadmap_id, user.id)
    # Same roadmap row lock as additions; deletion cannot race a cycle check.
    db.execute(
        update(Roadmap).where(Roadmap.id == roadmap_id).values(title=Roadmap.title)
    )
    db.execute(
        delete(RoadmapEdge).where(
            RoadmapEdge.roadmap_id == roadmap_id,
            RoadmapEdge.parent_id == parent_id,
            RoadmapEdge.child_id == child_id,
        )
    )
    _mark_replan_needed(db, user.id, roadmap_id)
    db.commit()


class PositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    x: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    y: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    pinned: bool = False


Positions = Annotated[list[PositionIn], Field(max_length=1000)]


class LayoutIn(BaseModel):
    positions: Positions


@router.put("/roadmaps/{roadmap_id}/graph/layout")
@router.put("/roadmaps/{roadmap_id}/layout", include_in_schema=False)
def put_layout(roadmap_id: str, data: Positions | LayoutIn, db: DB, user: CurrentUser):
    """Save this user's node positions: a bare list (spec 8) or the older {positions}."""
    _owned_roadmap(db, roadmap_id, user.id)
    positions = data if isinstance(data, list) else data.positions
    if not positions:
        return {"saved": 0}

    requested_ids = {position.node_id for position in positions}
    roadmap_node_ids = set(
        db.scalars(
            select(RoadmapNode.id).where(
                RoadmapNode.roadmap_id == roadmap_id,
                RoadmapNode.id.in_(requested_ids),
            )
        )
    )
    missing = requested_ids - roadmap_node_ids
    if missing:
        for position in positions:
            if position.node_id in missing:
                _node(db, position.node_id, user.id)
                raise HTTPException(422, "node_outside_roadmap")

    existing = {
        row.node_id: row
        for row in db.scalars(
            select(GraphLayout).where(
                GraphLayout.user_id == user.id,
                GraphLayout.node_id.in_(requested_ids),
            )
        )
    }
    now = utcnow()
    latest_by_node = {position.node_id: position for position in positions}
    new_rows: list[GraphLayout] = []
    for node_id, position in latest_by_node.items():
        row = existing.get(node_id)
        if row is None:
            new_rows.append(
                GraphLayout(
                    user_id=user.id,
                    node_id=node_id,
                    x=position.x,
                    y=position.y,
                    pinned=position.pinned,
                    updated_at=now,
                )
            )
        else:
            row.x = position.x
            row.y = position.y
            row.pinned = position.pinned
            row.updated_at = now
    if new_rows:
        db.add_all(new_rows)
    db.commit()
    return {"saved": len(positions)}


@router.get("/roadmaps/{roadmap_id}/graph/layout")
@router.get("/roadmaps/{roadmap_id}/layout", include_in_schema=False)
def get_layout(roadmap_id: str, db: DB, user: CurrentUser):
    _owned_roadmap(db, roadmap_id, user.id)
    rows = db.scalars(
        select(GraphLayout)
        .join(RoadmapNode, GraphLayout.node_id == RoadmapNode.id)
        .where(GraphLayout.user_id == user.id, RoadmapNode.roadmap_id == roadmap_id)
    )
    return {
        "positions": [
            {"node_id": r.node_id, "x": r.x, "y": r.y, "pinned": r.pinned} for r in rows
        ]
    }
