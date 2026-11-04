"""Core loop endpoints: syllabus, roadmap generation and scheduling (issue #63, spec 8.1-8.4).

HTTP and storage only (ADR 003): parsing lives in app.syllabus, node rules in
app.roadmap, and scheduling goes through services.schedule_roadmap to the shared planner.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select

from app.ingest import InvalidDocument, TextFormat
from app.llm import RetryableError, get_client
from app.roadmap import decode_covers, derive_nodes, link, node_spec
from app.syllabus import (
    InvalidSyllabusResponse,
    NotASyllabus,
    extract_syllabus,
    parse_syllabus,
)

from .dependencies import DB, CurrentUser
from .models import (
    Assessment,
    Course,
    LearningOutcome,
    Roadmap,
    RoadmapNode,
    Source,
    Syllabus,
)
from .routes_courses import owned_course
from .schemas import (
    RoadmapGenerateIn,
    RoadmapOut,
    RoadmapScheduleIn,
    RoadmapScheduleOut,
    SyllabusIn,
    SyllabusOut,
    SyllabusParseIn,
)
from .services import schedule_roadmap as plan_roadmap
from .services import serialize_schedule_changes

router = APIRouter(tags=["Syllabus and roadmap"])


# --- Syllabus ----------------------------------------------------------------


@router.post("/courses/{course_id}/syllabus:parse")
def preview_syllabus(course_id: str, data: SyllabusParseIn, db: DB, user: CurrentUser):
    """#59 parsing preview: no persistence or confirmation of model output.

    Upload PDF/DOCX/text through /sources with kind=syllabus, then pass file_name;
    pasted text can be parsed directly. Page numbers are local to that one file.
    """
    owned_course(db, course_id, user.id)
    if (data.text is None) == (data.file_name is None):
        raise HTTPException(422, "provide_text_or_file_name")
    if data.text is not None:
        try:
            pages = TextFormat().read(data.text.encode("utf-8"))
        except InvalidDocument:
            raise HTTPException(422, "not_a_syllabus") from None
    else:
        sources = db.scalars(select(Source).where(
            Source.course_id == course_id, Source.file_name == data.file_name,
            Source.kind == "syllabus",
        ).order_by(Source.page)).all()
        if not sources:
            raise HTTPException(404, "no_syllabus_sources")
        if [s.page for s in sources] != list(range(1, len(sources) + 1)):
            raise HTTPException(409, "invalid_source_pages")
        pages = [s.text for s in sources]
    try:
        draft = extract_syllabus(pages, get_client() if data.use_llm else None)
    except NotASyllabus:
        raise HTTPException(422, "not_a_syllabus") from None
    except InvalidSyllabusResponse:
        raise HTTPException(502, "invalid_llm_response") from None
    except (RetryableError, RuntimeError):
        raise HTTPException(503, "llm_unavailable") from None
    except ValueError:
        raise HTTPException(422, "invalid_syllabus") from None
    return {**draft.to_dict(), "file_name": data.file_name}


def _latest_syllabus(db, course_id: str) -> Syllabus | None:
    return db.scalars(
        select(Syllabus)
        .where(Syllabus.course_id == course_id)
        .order_by(Syllabus.created_at.desc(), Syllabus.id.desc())
    ).first()


def _course_syllabus(db, course_id: str, syllabus_id: str) -> Syllabus:
    syllabus = db.get(Syllabus, syllabus_id)
    if syllabus is None or syllabus.course_id != course_id:
        raise HTTPException(404, "Syllabus not found")
    return syllabus


def _syllabus_children(db, syllabus_id: str):
    outcomes = db.scalars(
        select(LearningOutcome)
        .where(LearningOutcome.syllabus_id == syllabus_id)
        .order_by(LearningOutcome.code, LearningOutcome.id)
    ).all()
    assessments = db.scalars(
        select(Assessment)
        .where(Assessment.syllabus_id == syllabus_id)
        .order_by(Assessment.due_week, Assessment.name, Assessment.id)
    ).all()
    return outcomes, assessments


def _save_syllabus(
    db, course_id: str, data: SyllabusIn | None, syllabus: Syllabus | None = None
) -> dict:
    """Create or partially update a syllabus; omitted parts keep what is stored."""
    data = data or SyllabusIn()
    parts = parse_syllabus(data.model_dump(), data.model_fields_set)
    if syllabus is None:
        syllabus = Syllabus(course_id=course_id, raw_text=parts.raw_text or "")
        db.add(syllabus)
        db.flush()
    elif parts.raw_text is not None:
        syllabus.raw_text = parts.raw_text
    if parts.outcomes is not None:
        db.execute(
            delete(LearningOutcome).where(LearningOutcome.syllabus_id == syllabus.id)
        )
        db.add_all(
            LearningOutcome(syllabus_id=syllabus.id, **asdict(row))
            for row in parts.outcomes
        )
    if parts.assessments is not None:
        db.execute(delete(Assessment).where(Assessment.syllabus_id == syllabus.id))
        db.add_all(
            Assessment(syllabus_id=syllabus.id, **asdict(row))
            for row in parts.assessments
        )
    db.commit()
    return _syllabus_payload(db, syllabus)


def _syllabus_payload(db, syllabus: Syllabus) -> dict:
    outcomes, assessments = _syllabus_children(db, syllabus.id)
    return {
        "id": syllabus.id,
        "syllabus_id": syllabus.id,
        "course_id": syllabus.course_id,
        "raw_text": syllabus.raw_text,
        "created_at": syllabus.created_at,
        "learning_outcomes": outcomes,
        "assessments": assessments,
    }


@router.get("/courses/{course_id}/syllabus", response_model=SyllabusOut)
def get_syllabus(course_id: str, db: DB, user: CurrentUser):
    owned_course(db, course_id, user.id)
    syllabus = _latest_syllabus(db, course_id)
    if syllabus is None:
        raise HTTPException(404, "Syllabus not found")
    return _syllabus_payload(db, syllabus)


@router.post(
    "/courses/{course_id}/syllabus", response_model=SyllabusOut, status_code=201
)
def create_syllabus(
    course_id: str, db: DB, user: CurrentUser, data: SyllabusIn | None = None
):
    owned_course(db, course_id, user.id)
    return _save_syllabus(db, course_id, data)


@router.put("/courses/{course_id}/syllabus", response_model=SyllabusOut)
def update_syllabus(
    course_id: str, db: DB, user: CurrentUser, data: SyllabusIn | None = None
):
    """Updates ``syllabus_id`` from the body, else the latest syllabus (or creates one)."""
    owned_course(db, course_id, user.id)
    if data is not None and data.syllabus_id:
        syllabus = _course_syllabus(db, course_id, data.syllabus_id)
    else:
        syllabus = _latest_syllabus(db, course_id)
    return _save_syllabus(db, course_id, data, syllabus)


@router.put(
    "/courses/{course_id}/syllabus/{syllabus_id}", response_model=SyllabusOut
)
def update_syllabus_by_id(
    course_id: str,
    syllabus_id: str,
    db: DB,
    user: CurrentUser,
    data: SyllabusIn | None = None,
):
    """Spec 8.2's path; the course-scoped PUT above does the same for the latest one."""
    owned_course(db, course_id, user.id)
    syllabus = _course_syllabus(db, course_id, syllabus_id)
    return _save_syllabus(db, course_id, data, syllabus)


# --- Roadmap -----------------------------------------------------------------


def _owned_roadmap(db, roadmap_id: str, user_id: str) -> Roadmap:
    roadmap = db.get(Roadmap, roadmap_id)
    course = roadmap and db.get(Course, roadmap.course_id)
    if roadmap is None or roadmap.user_id != user_id or course is None or (
        course.owner_id != user_id
    ):
        raise HTTPException(404, "Roadmap not found")
    return roadmap


def _roadmap_nodes(db, roadmap_id: str) -> list[RoadmapNode]:
    return list(
        db.scalars(
            select(RoadmapNode)
            .where(RoadmapNode.roadmap_id == roadmap_id)
            .order_by(RoadmapNode.week, RoadmapNode.id)
        )
    )


def _roadmap_payload(roadmap: Roadmap, nodes: list[RoadmapNode]) -> dict:
    return {
        "id": roadmap.id,
        "roadmap_id": roadmap.id,
        "course_id": roadmap.course_id,
        "user_id": roadmap.user_id,
        "title": roadmap.title,
        "created_at": roadmap.created_at,
        "nodes": [
            {
                "id": node.id,
                "roadmap_id": node.roadmap_id,
                "type": node.type,
                "kind": node.type,
                "title": node.title,
                "week": node.week,
                "duration_minutes": node.duration_minutes,
                "est_minutes": node.duration_minutes,
                "due_at": node.due_at,
                "covers": decode_covers(node.covers),
            }
            for node in nodes
        ],
    }


@router.post(
    "/courses/{course_id}/roadmap:generate",
    response_model=RoadmapOut,
    status_code=201,
)
def generate_roadmap(
    course_id: str,
    db: DB,
    user: CurrentUser,
    data: RoadmapGenerateIn | None = None,
):
    """Nodes from the body, else derived from the syllabus (the given or latest one)."""
    course = owned_course(db, course_id, user.id)
    data = data or RoadmapGenerateIn()
    syllabus = (
        _course_syllabus(db, course_id, data.syllabus_id)
        if data.syllabus_id
        else _latest_syllabus(db, course_id)
    )
    if data.nodes:
        specs = [node_spec(node.model_dump()) for node in data.nodes]
    elif syllabus is not None:
        outcomes, assessments = _syllabus_children(db, syllabus.id)
        specs = derive_nodes(
            [row.description or row.code for row in outcomes],
            [(row.name, row.due_week) for row in assessments],
            syllabus.raw_text,
        )
    else:
        specs = []

    roadmap = Roadmap(
        course_id=course_id,
        user_id=user.id,
        title=data.title or f"{course.title} roadmap",
    )
    db.add(roadmap)
    db.flush()
    nodes = [
        RoadmapNode(
            id=spec.id,
            roadmap_id=roadmap.id,
            type=spec.kind,
            title=spec.title,
            week=spec.week,
            duration_minutes=spec.duration_minutes,
            due_at=spec.due_at,
            covers=None if spec.covers is None else json.dumps(spec.covers),
        )
        for spec in link(specs)
    ]
    db.add_all(nodes)
    db.commit()
    return _roadmap_payload(roadmap, nodes)


@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapOut)
def get_roadmap(roadmap_id: str, db: DB, user: CurrentUser):
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    return _roadmap_payload(roadmap, _roadmap_nodes(db, roadmap.id))


@router.post("/roadmaps/{roadmap_id}:schedule", response_model=RoadmapScheduleOut)
@serialize_schedule_changes
def schedule_roadmap(
    roadmap_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
    data: RoadmapScheduleIn | None = None,
):
    """One task per node, then sessions from the shared planner; nodes that do not fit
    before their deadline come back in ``unscheduled`` and their weeks in
    ``overloaded_weeks``."""
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    nodes = _roadmap_nodes(db, roadmap.id)
    if not nodes:
        return {"roadmap_id": roadmap.id}
    data = data or RoadmapScheduleIn()
    tasks, sessions, plan = plan_roadmap(
        db, user, roadmap, nodes, data.max_daily_minutes, data.starts_at,
        request.app.state.now(),
    )
    return {
        "roadmap_id": roadmap.id,
        "tasks": tasks,
        "sessions": sessions,
        "entries": sessions,
        "unscheduled": plan.unscheduled,
        "overloaded_weeks": plan.overloaded_weeks,
    }
