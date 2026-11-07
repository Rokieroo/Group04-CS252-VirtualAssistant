"""Node learning sources, quoted exercises and graph write contracts."""

import json
from collections import defaultdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from app.roadmap import (
    layers,
    local_graph,
    prerequisites,
    transitive_reduction,
)

from .catalog_models import Concept, GraphLayout, RoadmapEdge
from .catalog_repository import node_sources
from .dependencies import DB, CurrentUser
from .exercise_repository import exercises_for_node
from .material_repository import decide, node_materials
from .models import (
    Course,
    LearningOutcome,
    Notification,
    Roadmap,
    RoadmapNode,
    Source,
    Syllabus,
    Task,
)
from .roadmap_repository import CycleError, add_roadmap_edge, owned_node, save_layout
from .routes_core import _owned_roadmap
from .schemas import GraphEdgeOut, GraphNodeOut, RoadmapGraphOut

router = APIRouter(tags=["Node learning and graph"])

_edge_edit_history: dict[str, list[float]] = defaultdict(list)


def _check_edge_rate_limit(user_id: str, now_ts: float):
    window_start = now_ts - 60.0
    history = [t for t in _edge_edit_history[user_id] if t >= window_start]
    if len(history) >= 120:
        raise HTTPException(
            429,
            "Edge edit rate limit reached (120/min)",
            headers={"Retry-After": "60"},
        )
    history.append(now_ts)
    _edge_edit_history[user_id] = history


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
) -> RoadmapGraphOut:
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
        return RoadmapGraphOut(nodes=[], edges=[])

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
        {c.id: c for c in db.scalars(select(Concept).where(Concept.id.in_(concept_ids)))}
        if concept_ids
        else {}
    )

    syllabus = db.scalar(
        select(Syllabus)
        .where(Syllabus.course_id == course.id)
        .order_by(Syllabus.created_at.desc())
        .limit(1)
    )
    outcomes = (
        list(db.scalars(select(LearningOutcome).where(LearningOutcome.syllabus_id == syllabus.id)))
        if syllabus
        else []
    )

    sources_by_node = node_sources(db, nodes, roadmap, course, now)

    stored_edges = list(
        db.scalars(select(RoadmapEdge).where(RoadmapEdge.roadmap_id == roadmap_id))
    )

    milestone_needs = prerequisites(nodes)
    covers_edges: list[GraphEdgeOut] = []
    for milestone_id, covered_topics in milestone_needs.items():
        for parent_topic_id in covered_topics:
            covers_edges.append(
                GraphEdgeOut(
                    parent=parent_topic_id,
                    child=milestone_id,
                    kind="covers",
                    origin="milestone_covers",
                    confidence=1.0,
                    reason="Milestone covers topic",
                    parent_id=parent_topic_id,
                    child_id=milestone_id,
                )
            )

    all_edge_models: list[GraphEdgeOut] = [
        GraphEdgeOut(
            parent=e.parent_id,
            child=e.child_id,
            kind=e.kind,
            origin=e.origin,
            confidence=e.confidence,
            reason=e.reason,
            parent_id=e.parent_id,
            child_id=e.child_id,
        )
        for e in stored_edges
    ] + covers_edges

    layer_map = layers(nodes, all_edge_models)

    if reduce:
        final_edges = transitive_reduction(nodes, all_edge_models)
    else:
        final_edges = all_edge_models

    node_outs: list[GraphNodeOut] = []
    for node in nodes:
        c = concepts.get(node.concept_id) if node.concept_id else None
        sp: list[int] = []
        if c and c.source_pages:
            try:
                sp = json.loads(c.source_pages) if isinstance(c.source_pages, str) else list(c.source_pages)
            except (ValueError, TypeError):
                sp = []

        t = tasks.get(node.id)
        user_status = t.status if t else "pending"

        s_summary = sources_by_node.get(node.id, {})
        s_count = s_summary.get("source_count", 0)
        um_count = s_summary.get("user_material_count", 0)
        s_status = s_summary.get("status", "insufficient")

        matched_outcomes = [
            o.id
            for o in outcomes
            if (o.code and o.code.lower() in node.title.lower())
            or (o.description and o.description.lower() in node.title.lower())
        ]

        node_outs.append(
            GraphNodeOut(
                id=node.id,
                type=node.type,
                kind=node.type,
                title=node.title,
                week=node.week,
                est_minutes=node.duration_minutes,
                due_at=node.due_at,
                outcome_ids=matched_outcomes,
                source_pages=sp,
                status=user_status,
                source_count=s_count,
                user_material_count=um_count,
                sources_status=s_status,
                layer=layer_map.get(node.id, node.week or 1),
            )
        )

    return RoadmapGraphOut(nodes=node_outs, edges=final_edges)


@router.get("/roadmaps/{roadmap_id}/graph", response_model=RoadmapGraphOut)
def get_roadmap_graph(
    roadmap_id: str,
    db: DB,
    user: CurrentUser,
    request: Request,
    reduce: bool = Query(False),
):
    """Retrieve full course roadmap graph (issue #103, spec 8, UC-03)."""
    return _build_roadmap_graph(db, roadmap_id, user.id, request.app.state.now(), reduce=reduce)


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
    full_graph = _build_roadmap_graph(db, roadmap.id, user.id, request.app.state.now(), reduce=False)
    sub_node_ids, sub_edges = local_graph(
        full_graph.nodes, full_graph.edges, node_id, depth=depth, direction=direction
    )
    sub_nodes_set = set(sub_node_ids)
    sub_nodes = [n for n in full_graph.nodes if n.id in sub_nodes_set]
    return RoadmapGraphOut(nodes=sub_nodes, edges=sub_edges)


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: str | None = None
    child_id: str | None = None
    parent: str | None = None
    child: str | None = None
    kind: Literal["soft", "strict"] = "strict"
    reason: str = Field("", max_length=300)

    @model_validator(mode="after")
    def _validate_endpoints(self):
        p = self.parent or self.parent_id
        c = self.child or self.child_id
        if not p or not c:
            raise ValueError("parent and child endpoints are required")
        self.parent = p
        self.child = c
        self.parent_id = p
        self.child_id = c
        return self


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


@router.post(
    "/roadmaps/{roadmap_id}/graph/edges",
    status_code=201,
    responses={
        409: {"description": "Dependency cycle detected"},
        429: {"description": "Rate limit exceeded"},
    },
)
@router.post(
    "/roadmaps/{roadmap_id}/edges",
    status_code=201,
    responses={
        409: {"description": "Dependency cycle detected"},
        429: {"description": "Rate limit exceeded"},
    },
)
def add_edge(
    roadmap_id: str,
    data: EdgeIn,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Add directed dependency edge to roadmap DAG (issue #103)."""
    _check_edge_rate_limit(user.id, request.app.state.now().timestamp())
    _owned_roadmap(db, roadmap_id, user.id)
    try:
        edge = add_roadmap_edge(
            db,
            roadmap_id,
            parent_id=data.parent,
            child_id=data.child,
            kind=data.kind,
            origin="user",
            confidence=1.0,
            reason=data.reason,
            created_by=user.id,
        )
        existing_notif = db.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.message.like(f"Roadmap {roadmap_id} edges updated%"),
                Notification.read.is_(False),
            )
        )
        if not existing_notif:
            db.add(
                Notification(
                    user_id=user.id,
                    message=f"Roadmap {roadmap_id} edges updated; schedule replan required.",
                )
            )
        db.commit()
        return {
            "parent": edge.parent_id,
            "child": edge.child_id,
            "parent_id": edge.parent_id,
            "child_id": edge.child_id,
            "kind": edge.kind,
            "origin": edge.origin,
            "confidence": edge.confidence,
            "reason": edge.reason,
        }
    except CycleError as exc:
        db.rollback()
        raise HTTPException(
            409, detail={"error": "cycle", "code": "dependency_cycle", "path": exc.path}
        ) from None
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None


@router.delete("/roadmaps/{roadmap_id}/graph/edges/{parent_id}/{child_id}", status_code=204)
@router.delete("/roadmaps/{roadmap_id}/edges/{parent_id}/{child_id}", status_code=204)
def remove_edge(
    roadmap_id: str,
    parent_id: str,
    child_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Remove directed dependency edge from roadmap DAG (issue #103)."""
    _check_edge_rate_limit(user.id, request.app.state.now().timestamp())
    _owned_roadmap(db, roadmap_id, user.id)
    from sqlalchemy import update

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
    existing_notif = db.scalar(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.message.like(f"Roadmap {roadmap_id} edges updated%"),
            Notification.read.is_(False),
        )
    )
    if not existing_notif:
        db.add(
            Notification(
                user_id=user.id,
                message=f"Roadmap {roadmap_id} edges updated; schedule replan required.",
            )
        )
    db.commit()


class PositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    x: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    y: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    pinned: bool = False


class LayoutIn(BaseModel):
    positions: list[PositionIn] = Field(max_length=1000)


@router.put("/roadmaps/{roadmap_id}/graph/layout")
@router.put("/roadmaps/{roadmap_id}/layout")
def put_layout(
    roadmap_id: str,
    data: list[PositionIn] | LayoutIn,
    db: DB,
    user: CurrentUser,
):
    """Save graph layout coordinates for user (issue #103)."""
    _owned_roadmap(db, roadmap_id, user.id)
    positions = data if isinstance(data, list) else data.positions
    if len(positions) > 1000:
        raise HTTPException(422, "at_most_1000_positions")
    for position in positions:
        node, _, _ = _node(db, position.node_id, user.id)
        if node.roadmap_id != roadmap_id:
            raise HTTPException(422, "node_outside_roadmap")
        save_layout(db, user.id, **position.model_dump())
    db.commit()
    return {"saved": len(positions)}


@router.get("/roadmaps/{roadmap_id}/graph/layout")
@router.get("/roadmaps/{roadmap_id}/layout")
def get_layout(roadmap_id: str, db: DB, user: CurrentUser):
    """Get graph layout coordinates for user (issue #103)."""
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
