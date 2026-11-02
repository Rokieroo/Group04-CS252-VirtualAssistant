"""Core loop endpoints: syllabus upload, roadmap generation and scheduling (issue #63)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select

from .dependencies import DB, CurrentUser
from .models import (
    Assessment,
    Course,
    LearningOutcome,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Syllabus,
    Task,
)
from .routes_courses import owned_course
from .schemas import (
    RoadmapGenerateIn,
    RoadmapNodeIn,
    RoadmapOut,
    RoadmapScheduleIn,
    RoadmapScheduleOut,
    SyllabusIn,
    SyllabusOut,
)

router = APIRouter(tags=["Syllabus and roadmap"])


# ---------------------------------------------------------------------------
# Small coercion helpers: the schema column names are authoritative, but the
# phase 2 API contract also uses a few aliases (text/title/kind/est_minutes).
# ---------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return value.strip() if isinstance(value, str) else str(value).strip()


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def _number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    return float(match.group().replace(",", ".")) if match else 0.0


def _due_week(item: dict[str, Any]) -> int | None:
    value = _integer(item.get("due_week"))
    if value is not None:
        return value
    for key in ("due", "week"):
        raw = _text(item.get(key))
        if not raw:
            continue
        match = re.search(r"(?:week|tuần)\s*(\d+)", raw, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        if raw.isdigit():
            return int(raw)
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _covers(value: str | None) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


# ---------------------------------------------------------------------------
# Syllabus
# ---------------------------------------------------------------------------


def _syllabus_parts(
    data: SyllabusIn | None,
) -> tuple[str | None, list[dict] | None, list[dict] | None]:
    """Return ``(raw_text, outcomes, assessments)``; None means "leave alone".

    PUT is allowed to be partial. Explicit empty lists clear the children, while
    an omitted field preserves whatever is already stored.
    """

    if data is None:
        return None, None, None

    payload = data.model_dump()
    fields = data.model_fields_set
    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}

    raw: str | None = None
    if "raw_text" in fields:
        raw = _text(payload.get("raw_text")) or ""
    elif "text" in fields:
        raw = _text(payload.get("text")) or ""
    elif "parsed" in fields:
        raw = _text(parsed.get("raw_text")) or _text(parsed.get("text"))
        if raw is None:
            raw = json.dumps(parsed, ensure_ascii=False) if parsed else ""

    outcome_rows: list | None = None
    if "learning_outcomes" in fields:
        outcome_rows = payload.get("learning_outcomes") or []
    elif "outcomes" in fields:
        outcome_rows = payload.get("outcomes") or []
    elif "parsed" in fields and "outcomes" in parsed:
        outcome_rows = parsed.get("outcomes") or []

    assessment_rows: list | None = None
    if "assessments" in fields:
        assessment_rows = payload.get("assessments") or []
    elif "parsed" in fields and "assessments" in parsed:
        assessment_rows = parsed.get("assessments") or []

    outcomes: list[dict] | None = None
    if outcome_rows is not None:
        outcomes = []
        for index, item in enumerate(outcome_rows, start=1):
            if isinstance(item, str):
                item = {"description": item}
            row = _as_dict(item)
            code = _text(row.get("code"))
            description = _text(
                row.get("description") or row.get("text") or row.get("title")
            )
            if not code and not description:
                continue
            outcomes.append(
                {
                    "code": code or f"CLO{index}",
                    "description": description or code,
                    "bloom_level": _text(row.get("bloom_level")) or "understand",
                }
            )

    assessments: list[dict] | None = None
    if assessment_rows is not None:
        assessments = []
        for index, item in enumerate(assessment_rows, start=1):
            if isinstance(item, str):
                item = {"name": item}
            row = _as_dict(item)
            name = _text(row.get("name") or row.get("title"))
            if not name:
                name = f"Assessment {index}"
            assessments.append(
                {
                    "name": name,
                    "weight": _number(row.get("weight")),
                    "due_week": _due_week(row),
                }
            )
    return raw, outcomes, assessments


def _save_syllabus(
    db, course_id: str, data: SyllabusIn | None, syllabus: Syllabus | None = None
) -> tuple[Syllabus, list[LearningOutcome], list[Assessment]]:
    raw_text, outcome_rows, assessment_rows = _syllabus_parts(data)
    if syllabus is None:
        syllabus = Syllabus(course_id=course_id, raw_text=raw_text or "")
        db.add(syllabus)
        db.flush()
    elif raw_text is not None:
        syllabus.raw_text = raw_text

    if outcome_rows is not None:
        db.execute(
            delete(LearningOutcome).where(LearningOutcome.syllabus_id == syllabus.id)
        )
        outcomes = [
            LearningOutcome(syllabus_id=syllabus.id, **row) for row in outcome_rows
        ]
        db.add_all(outcomes)
    else:
        outcomes = list(
            db.scalars(
                select(LearningOutcome).where(
                    LearningOutcome.syllabus_id == syllabus.id
                )
            ).all()
        )

    if assessment_rows is not None:
        db.execute(delete(Assessment).where(Assessment.syllabus_id == syllabus.id))
        assessments = [
            Assessment(syllabus_id=syllabus.id, **row) for row in assessment_rows
        ]
        db.add_all(assessments)
    else:
        assessments = list(
            db.scalars(
                select(Assessment).where(Assessment.syllabus_id == syllabus.id)
            ).all()
        )

    db.flush()
    return syllabus, outcomes, assessments


def _syllabus_payload(
    syllabus: Syllabus,
    outcomes: list[LearningOutcome],
    assessments: list[Assessment],
) -> dict:
    return {
        "id": syllabus.id,
        "syllabus_id": syllabus.id,
        "course_id": syllabus.course_id,
        "raw_text": syllabus.raw_text,
        "created_at": syllabus.created_at,
        "learning_outcomes": [
            {
                "id": row.id,
                "syllabus_id": row.syllabus_id,
                "code": row.code,
                "description": row.description,
                "bloom_level": row.bloom_level,
            }
            for row in outcomes
        ],
        "assessments": [
            {
                "id": row.id,
                "syllabus_id": row.syllabus_id,
                "name": row.name,
                "weight": row.weight,
                "due_week": row.due_week,
            }
            for row in assessments
        ],
    }


def _latest_syllabus(db, course_id: str) -> Syllabus | None:
    return db.scalars(
        select(Syllabus)
        .where(Syllabus.course_id == course_id)
        .order_by(Syllabus.created_at.desc(), Syllabus.id.desc())
    ).first()


def _syllabus_children(
    db, syllabus_id: str
) -> tuple[list[LearningOutcome], list[Assessment]]:
    outcomes = list(
        db.scalars(
            select(LearningOutcome).where(
                LearningOutcome.syllabus_id == syllabus_id
            )
        ).all()
    )
    assessments = list(
        db.scalars(
            select(Assessment).where(Assessment.syllabus_id == syllabus_id)
        ).all()
    )
    return outcomes, assessments


@router.get("/courses/{course_id}/syllabus", response_model=SyllabusOut)
def get_syllabus(course_id: str, db: DB, user: CurrentUser):
    owned_course(db, course_id, user.id)
    syllabus = _latest_syllabus(db, course_id)
    if syllabus is None:
        raise HTTPException(404, "Syllabus not found")
    outcomes, assessments = _syllabus_children(db, syllabus.id)
    return _syllabus_payload(syllabus, outcomes, assessments)


@router.post(
    "/courses/{course_id}/syllabus", response_model=SyllabusOut, status_code=201
)
def create_syllabus(
    course_id: str,
    db: DB,
    user: CurrentUser,
    data: SyllabusIn | None = None,
):
    owned_course(db, course_id, user.id)
    syllabus, outcomes, assessments = _save_syllabus(db, course_id, data)
    db.commit()
    return _syllabus_payload(syllabus, outcomes, assessments)


@router.put("/courses/{course_id}/syllabus", response_model=SyllabusOut)
def update_syllabus(
    course_id: str,
    db: DB,
    user: CurrentUser,
    data: SyllabusIn | None = None,
):
    owned_course(db, course_id, user.id)
    syllabus = _latest_syllabus(db, course_id)
    if data is not None and data.syllabus_id:
        selected = db.get(Syllabus, data.syllabus_id)
        if selected is None or selected.course_id != course_id:
            raise HTTPException(404, "Syllabus not found")
        syllabus = selected
    syllabus, outcomes, assessments = _save_syllabus(
        db, course_id, data, syllabus=syllabus
    )
    db.commit()
    return _syllabus_payload(syllabus, outcomes, assessments)


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
    """Spec-compatible alias; the phase 2 issue uses the course-scoped PUT above."""
    owned_course(db, course_id, user.id)
    syllabus = db.get(Syllabus, syllabus_id)
    if syllabus is None or syllabus.course_id != course_id:
        raise HTTPException(404, "Syllabus not found")
    syllabus, outcomes, assessments = _save_syllabus(
        db, course_id, data, syllabus=syllabus
    )
    db.commit()
    return _syllabus_payload(syllabus, outcomes, assessments)


# ---------------------------------------------------------------------------
# Roadmap generation
# ---------------------------------------------------------------------------


def _parse_week_topics(raw_text: str) -> list[RoadmapNodeIn]:
    """Best-effort fallback for a pasted syllabus that has only week headings."""
    nodes: list[RoadmapNodeIn] = []
    pattern = re.compile(
        r"(?:week|tuần)\s*(\d+)\s*[:\-–—]\s*(.+)", flags=re.IGNORECASE
    )
    for line in raw_text.splitlines():
        match = pattern.search(line.strip())
        if not match:
            continue
        week = int(match.group(1))
        for topic in re.split(r"[,;|]", match.group(2)):
            title = topic.strip(" .")
            if title:
                nodes.append(
                    RoadmapNodeIn(type="topic", title=title, week=week)
                )
    return nodes


def _derived_nodes(db, syllabus: Syllabus | None) -> list[RoadmapNodeIn]:
    if syllabus is None:
        return []
    outcomes = db.scalars(
        select(LearningOutcome)
        .where(LearningOutcome.syllabus_id == syllabus.id)
        .order_by(LearningOutcome.code, LearningOutcome.id)
    ).all()
    assessments = db.scalars(
        select(Assessment)
        .where(Assessment.syllabus_id == syllabus.id)
        .order_by(Assessment.due_week, Assessment.name, Assessment.id)
    ).all()
    nodes = [
        RoadmapNodeIn(
            type="topic",
            title=row.description or row.code,
            duration_minutes=60,
        )
        for row in outcomes
    ]
    nodes += [
        RoadmapNodeIn(
            type="milestone",
            title=row.name,
            week=row.due_week,
            duration_minutes=30,
        )
        for row in assessments
    ]
    return nodes or _parse_week_topics(syllabus.raw_text)


def _create_nodes(db, roadmap: Roadmap, specs: list[RoadmapNodeIn]) -> list[RoadmapNode]:
    nodes: list[RoadmapNode] = []
    covered: list[str] = []
    for spec in specs:
        row = spec.model_dump()
        node_type = _text(row.get("type") or row.get("kind")) or "topic"
        if node_type not in {"topic", "milestone"}:
            node_type = "topic"
        title = _text(row.get("title") or row.get("description")) or "Untitled"
        week = _integer(row.get("week"))
        duration = _integer(
            row.get("duration_minutes")
            or row.get("est_minutes")
            or row.get("duration")
        )
        if duration is None:
            duration = 60 if node_type == "topic" else 30
        covers = row.get("covers")
        if covers is None and node_type == "milestone":
            covers = covered
        if covers is not None and not isinstance(covers, str):
            covers = json.dumps(covers, ensure_ascii=False)
        node_id = _text(row.get("id"))
        if not node_id or db.get(RoadmapNode, node_id) is not None:
            node_id = None
        values = {
            "roadmap_id": roadmap.id,
            "type": node_type,
            "title": title,
            "week": week,
            "duration_minutes": duration,
            "due_at": _datetime(row.get("due_at")),
            "covers": covers,
        }
        if node_id is not None:
            values["id"] = node_id
        node = RoadmapNode(**values)
        db.add(node)
        db.flush()
        nodes.append(node)
        if node_type == "topic":
            covered.append(node.id)
    return nodes


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
                "covers": _covers(node.covers),
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
    course = owned_course(db, course_id, user.id)
    payload = data or RoadmapGenerateIn()

    syllabus = None
    if payload.syllabus_id:
        syllabus = db.get(Syllabus, payload.syllabus_id)
        if syllabus is None or syllabus.course_id != course_id:
            raise HTTPException(404, "Syllabus not found")
    else:
        syllabus = _latest_syllabus(db, course_id)

    roadmap = Roadmap(
        course_id=course_id,
        user_id=user.id,
        title=payload.title or f"{course.title} roadmap",
    )
    db.add(roadmap)
    db.flush()

    specs = payload.nodes or _derived_nodes(db, syllabus)
    nodes = _create_nodes(db, roadmap, specs)
    db.commit()
    return _roadmap_payload(roadmap, nodes)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def _owned_roadmap(db, roadmap_id: str, user_id: str) -> Roadmap:
    roadmap = db.get(Roadmap, roadmap_id)
    if roadmap is None or roadmap.user_id != user_id:
        raise HTTPException(404, "Roadmap not found")
    course = db.get(Course, roadmap.course_id)
    if course is None or course.owner_id != user_id:
        raise HTTPException(404, "Roadmap not found")
    return roadmap


@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapOut)
def get_roadmap(roadmap_id: str, db: DB, user: CurrentUser):
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    nodes = db.scalars(
        select(RoadmapNode)
        .where(RoadmapNode.roadmap_id == roadmap.id)
        .order_by(RoadmapNode.week, RoadmapNode.id)
    ).all()
    return _roadmap_payload(roadmap, list(nodes))


def _task_due_at(node: RoadmapNode, now: datetime) -> datetime:
    if node.due_at is not None:
        return node.due_at
    return now + timedelta(days=7 * max(1, node.week or 1))


def _entry_payload(entry: ScheduleEntry) -> dict:
    return {
        "id": entry.id,
        "task_id": entry.task_id,
        "starts_at": entry.starts_at,
        "ends_at": entry.ends_at,
        "status": entry.status,
        "actual_minutes": entry.actual_minutes,
    }


@router.post("/roadmaps/{roadmap_id}:schedule", response_model=RoadmapScheduleOut)
def schedule_roadmap(
    roadmap_id: str,
    request: Request,
    db: DB,
    user: CurrentUser,
    data: RoadmapScheduleIn | None = None,
):
    roadmap = _owned_roadmap(db, roadmap_id, user.id)
    nodes = db.scalars(
        select(RoadmapNode)
        .where(RoadmapNode.roadmap_id == roadmap.id)
        .order_by(RoadmapNode.week, RoadmapNode.id)
    ).all()
    if not nodes:
        return {"roadmap_id": roadmap.id, "tasks": [], "sessions": [], "entries": []}

    now = request.app.state.now()
    options = data or RoadmapScheduleIn()
    node_ids = [node.id for node in nodes]
    existing = db.scalars(
        select(Task).where(
            Task.owner_id == user.id,
            Task.roadmap_node_id.in_(node_ids),
        )
    ).all()
    tasks_by_node = {task.roadmap_node_id: task for task in existing}

    tasks: list[Task] = []
    for node in nodes:
        task = tasks_by_node.get(node.id)
        if task is None:
            task = Task(
                owner_id=user.id,
                assignee_id=user.id,
                title=node.title,
                description=f"Roadmap: {roadmap.title}",
                duration_minutes=max(1, node.duration_minutes or 60),
                completed_minutes=0,
                priority=2,
                due_at=_task_due_at(node, now),
                status="pending",
                roadmap_node_id=node.id,
            )
            db.add(task)
        tasks.append(task)
    db.flush()

    task_ids = [task.id for task in tasks]
    entries = db.scalars(
        select(ScheduleEntry).where(ScheduleEntry.task_id.in_(task_ids))
    ).all()
    planned: dict[str, int] = {}
    for entry in entries:
        planned[entry.task_id] = planned.get(entry.task_id, 0) + int(
            (entry.ends_at - entry.starts_at).total_seconds() // 60
        )

    start = options.starts_at or now
    start = max(start, now)
    start = start.replace(hour=9, minute=0, second=0, microsecond=0)
    if start < now:
        start += timedelta(days=1)
    day_offset = 0
    max_daily = max(1, options.max_daily_minutes)

    for task in tasks:
        remaining = max(0, task.duration_minutes - planned.get(task.id, 0))
        while remaining > 0:
            chunk = min(remaining, max_daily)
            entry_start = start + timedelta(days=day_offset)
            entry_end = entry_start + timedelta(minutes=chunk)
            entry = ScheduleEntry(
                user_id=user.id,
                task_id=task.id,
                starts_at=entry_start,
                ends_at=entry_end,
                status="planned",
                actual_minutes=0,
            )
            db.add(entry)
            entries.append(entry)
            remaining -= chunk
            day_offset += 1

    db.commit()
    return {
        "roadmap_id": roadmap.id,
        "tasks": tasks,
        "sessions": [_entry_payload(entry) for entry in entries],
        "entries": [_entry_payload(entry) for entry in entries],
    }
