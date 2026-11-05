"""Core loop endpoints: syllabus, roadmap generation and scheduling (issue #63, spec 8.1-8.4).

HTTP and storage only (ADR 003): parsing lives in app.syllabus, node rules in
app.roadmap, and scheduling goes through services.schedule_roadmap to the shared planner.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select

from app.ingest import InvalidDocument, TextFormat
from app.llm import RetryableError, get_client
from app.planner import diff
from app.roadmap import decode_covers, derive_nodes, link, node_spec
from app.syllabus import (
    InvalidSyllabusResponse,
    NotASyllabus,
    parse_syllabus,
)
from app.syllabus import (
    preview_syllabus as parse_preview,
)

from .dependencies import DB, CurrentUser
from .models import (
    Assessment,
    Course,
    LearningOutcome,
    Notification,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Source,
    Syllabus,
    Task,
)
from .routes_courses import owned_course
from .schemas import (
    PlanRequest,
    ProposedEntry,
    RoadmapGenerateIn,
    RoadmapOut,
    RoadmapReplanIn,
    RoadmapReplanOut,
    RoadmapScheduleIn,
    RoadmapScheduleOut,
    SyllabusIn,
    SyllabusOut,
    SyllabusParseIn,
)
from .services import (
    MAX_PLAN_HORIZON,
    ROADMAP_SESSION_MINUTES,
    make_plan,
    serialize_schedule_changes,
    task_due_at,
)
from .services import schedule_roadmap as plan_roadmap

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
        draft = parse_preview(pages, get_client() if data.use_llm else None)
    except NotASyllabus:
        raise HTTPException(422, "not_a_syllabus") from None
    except InvalidSyllabusResponse:
        raise HTTPException(502, "invalid_llm_response") from None
    except (RetryableError, RuntimeError):
        raise HTTPException(503, "llm_unavailable") from None
    except ValueError:
        raise HTTPException(422, "invalid_syllabus") from None
    return {
        **draft.to_dict(),
        "file_name": data.file_name,
        "source_pages": {number: text for number, text in enumerate(pages, 1)},
    }


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



@router.post("/roadmaps/{roadmap_id}:replan", response_model=RoadmapReplanOut)
@serialize_schedule_changes
def replan_roadmap(
    roadmap_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
    data: RoadmapReplanIn | None = None,
):
    """Propose or commit schedule changes for this roadmap (spec 8.4, 10.5).

    Only pending sessions in the future are replanned; completed sessions and completed
    tasks are never touched. Rate-limited to 1 proposal per day.
    """
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    nodes = _roadmap_nodes(db, roadmap.id)
    if not nodes:
        return {"roadmap_id": roadmap.id, "diff": {}, "committed": False, "sessions": []}

    now = request.app.state.now()
    should_commit = bool(data and (data.approve or data.commit))

    if not should_commit:
        zone = ZoneInfo(user.timezone)
        user_today_start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        recent_proposal = db.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.message.like(f"Replan proposal for roadmap {roadmap.id}%"),
                Notification.created_at >= user_today_start,
            )
        )
        if recent_proposal is not None:
            raise HTTPException(
                429,
                "Only one replan proposal per day is allowed",
                headers={"Retry-After": "86400"},
            )

    existing = {
        task.roadmap_node_id: task
        for task in db.scalars(
            select(Task).where(
                Task.owner_id == user.id,
                Task.roadmap_node_id.in_([node.id for node in nodes]),
            )
        )
    }
    tasks = []
    for node in nodes:
        task = existing.get(node.id)
        if task is None:
            task = Task(
                owner_id=user.id,
                assignee_id=user.id,
                title=node.title,
                description=f"Roadmap: {roadmap.title}",
                duration_minutes=max(1, node.duration_minutes or 60),
                priority=2,
                due_at=task_due_at(node.due_at, node.week, now),
                roadmap_node_id=node.id,
            )
            db.add(task)
        tasks.append(task)
    db.flush()

    task_ids = {task.id for task in tasks}
    old_sessions = list(
        db.scalars(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.user_id == user.id,
                ScheduleEntry.task_id.in_(task_ids),
                ScheduleEntry.status == "planned",
                ScheduleEntry.starts_at >= now,
            )
            .order_by(ScheduleEntry.starts_at)
        ).all()
    )

    starts_at = data.starts_at if data else None
    start = max(starts_at or now, now)
    if start.second or start.microsecond:
        start = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    latest_due = max(task.due_at for task in tasks).replace(second=0, microsecond=0)
    shortest, longest = ROADMAP_SESSION_MINUTES
    max_daily = data.max_daily_minutes if (data and data.max_daily_minutes) else 120

    plan_request = PlanRequest(
        starts_at=start,
        ends_at=min(start + MAX_PLAN_HORIZON, max(latest_due, start + timedelta(days=1))),
        min_session_minutes=shortest,
        max_session_minutes=longest,
        daily_limit_minutes=max_daily,
        commit=should_commit,
    )

    plan = make_plan(db, user, plan_request, now)
    new_sessions = [e for e in plan.entries if e.task_id in task_ids]
    plan_diff = diff(old_sessions, new_sessions)

    if should_commit:
        committed_sessions = list(
            db.scalars(
                select(ScheduleEntry)
                .where(
                    ScheduleEntry.user_id == user.id,
                    ScheduleEntry.task_id.in_(task_ids),
                    ScheduleEntry.status == "planned",
                )
                .order_by(ScheduleEntry.starts_at)
            ).all()
        )
        sessions = [
            ProposedEntry(task_id=s.task_id, starts_at=s.starts_at, ends_at=s.ends_at)
            for s in committed_sessions
        ]
    else:
        db.add(
            Notification(
                user_id=user.id,
                created_at=now,
                message=f"Replan proposal for roadmap {roadmap.id} generated.",
            )
        )
        db.commit()
        sessions = [
            ProposedEntry(task_id=s.task_id, starts_at=s.starts_at, ends_at=s.ends_at)
            for s in new_sessions
        ]

    return {
        "roadmap_id": roadmap.id,
        "diff": {
            "moved": plan_diff.moved,
            "added": plan_diff.added,
            "dropped": plan_diff.dropped,
        },
        "committed": should_commit,
        "sessions": sessions,
    }
