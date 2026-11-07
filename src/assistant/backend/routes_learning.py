"""Node learning sources, quoted exercises and graph write contracts."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from .catalog_models import GraphLayout, RoadmapEdge
from .catalog_repository import node_sources
from .dependencies import DB, CurrentUser
from .exercise_repository import exercises_for_node
from .material_repository import decide, node_materials
from .models import RoadmapNode, Source
from .roadmap_repository import CycleError, add_roadmap_edge, owned_node, save_layout
from .routes_core import _owned_roadmap

router = APIRouter(tags=["Node learning and graph"])


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
    from .models import Course

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


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: str
    child_id: str
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


@router.post("/roadmaps/{roadmap_id}/edges", status_code=201)
def add_edge(roadmap_id: str, data: EdgeIn, db: DB, user: CurrentUser):
    _owned_roadmap(db, roadmap_id, user.id)
    try:
        edge = add_roadmap_edge(db, roadmap_id, **data.model_dump(), created_by=user.id)
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
        raise HTTPException(
            409, {"code": "dependency_cycle", "path": exc.path}
        ) from None
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None


@router.delete("/roadmaps/{roadmap_id}/edges/{parent_id}/{child_id}", status_code=204)
def remove_edge(
    roadmap_id: str, parent_id: str, child_id: str, db: DB, user: CurrentUser
):
    _owned_roadmap(db, roadmap_id, user.id)
    # Same roadmap row lock as additions; deletion cannot race a cycle check.
    from sqlalchemy import update

    from .models import Roadmap

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
    db.commit()


class PositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    x: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    y: float = Field(allow_inf_nan=False, ge=-1e7, le=1e7)
    pinned: bool = False


class LayoutIn(BaseModel):
    positions: list[PositionIn] = Field(max_length=1000)


@router.put("/roadmaps/{roadmap_id}/layout")
def put_layout(roadmap_id: str, data: LayoutIn, db: DB, user: CurrentUser):
    _owned_roadmap(db, roadmap_id, user.id)
    for position in data.positions:
        node, _, _ = _node(db, position.node_id, user.id)
        if node.roadmap_id != roadmap_id:
            raise HTTPException(422, "node_outside_roadmap")
        save_layout(db, user.id, **position.model_dump())
    db.commit()
    return {"saved": len(data.positions)}


@router.get("/roadmaps/{roadmap_id}/layout")
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
