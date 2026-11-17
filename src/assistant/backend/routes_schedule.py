"""Availability, calendar, planning/replanning, check-ins and reminders."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.planner import merge, minutes

from .dependencies import DB, CurrentUser
from .models import (
    Availability,
    BusyBlock,
    Notification,
    ReviewCard,
    ReviewLog,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Task,
    User,
)
from .schemas import (
    AvailabilityPut,
    BusyCreate,
    BusyOut,
    CheckIn,
    EntryOut,
    NotificationOut,
    PlanOut,
    PlanRequest,
    ReportOut,
    WindowOut,
)
from .services import (
    invalidate_future,
    make_plan,
    progress_report,
    serialize_schedule_changes,
)

router = APIRouter(tags=["Schedule"])


@router.put("/availability", response_model=list[WindowOut])
@serialize_schedule_changes
def put_availability(
    data: AvailabilityPut, request: Request, db: DB, user: CurrentUser
):
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    windows = merge([(window.starts_at, window.ends_at) for window in data.windows])
    db.execute(delete(Availability).where(Availability.user_id == user.id))
    rows = [
        Availability(user_id=user.id, starts_at=start, ends_at=end)
        for start, end in windows
    ]
    db.add_all(rows)
    # Changing availability explicitly invalidates only future, unchecked sessions.
    invalidate_future(db, user.id, request.app.state.now())
    db.commit()
    return rows


@router.get("/availability", response_model=list[WindowOut])
def get_availability(db: DB, user: CurrentUser):
    return db.scalars(
        select(Availability)
        .where(Availability.user_id == user.id)
        .order_by(Availability.starts_at)
    ).all()


@router.post("/busy-blocks", response_model=BusyOut, status_code=201)
@serialize_schedule_changes
def create_busy_block(data: BusyCreate, request: Request, db: DB, user: CurrentUser):
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    block = BusyBlock(user_id=user.id, **data.model_dump())
    db.add(block)
    db.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.user_id == user.id,
            ScheduleEntry.status == "planned",
            ScheduleEntry.starts_at >= request.app.state.now(),
            ScheduleEntry.starts_at < data.ends_at,
            ScheduleEntry.ends_at > data.starts_at,
        )
    )
    db.commit()
    return block


@router.get("/busy-blocks", response_model=list[BusyOut])
def list_busy_blocks(db: DB, user: CurrentUser):
    return db.scalars(
        select(BusyBlock)
        .where(BusyBlock.user_id == user.id)
        .order_by(BusyBlock.starts_at)
    ).all()


@router.delete("/busy-blocks/{block_id}", status_code=204)
@serialize_schedule_changes
def delete_busy_block(block_id: str, request: Request, db: DB, user: CurrentUser):
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    block = db.get(BusyBlock, block_id)
    if block is None or block.user_id != user.id:
        raise HTTPException(404, "Busy block not found")
    db.delete(block)
    db.commit()
    return Response(status_code=204)


def plan_schedule(data: PlanRequest, request: Request, db: DB, user: CurrentUser):
    if data.starts_at < request.app.state.now().replace(second=0, microsecond=0):
        raise HTTPException(422, "A plan must start now or in the future")
    with request.app.state.schedule_lock:
        return make_plan(db, user, data, request.app.state.now())


router.add_api_route(
    "/schedule/plan",
    plan_schedule,
    methods=["POST"],
    response_model=PlanOut,
    summary="Preview or commit a schedule (UC-02, UC-03)",
)
router.add_api_route(
    "/schedule/replan",
    plan_schedule,
    methods=["POST"],
    response_model=PlanOut,
    summary="Replan unchecked sessions; preserve check-ins (UC-06)",
)


@router.get("/schedule", response_model=list[EntryOut])
def calendar(
    db: DB,
    user: CurrentUser,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
):
    for value in (starts_at, ends_at):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(422, "Calendar timestamps require an offset")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise HTTPException(422, "ends_at must be after starts_at")
    query = select(ScheduleEntry).where(ScheduleEntry.user_id == user.id)
    if starts_at is not None:
        query = query.where(ScheduleEntry.ends_at > starts_at)
    if ends_at is not None:
        query = query.where(ScheduleEntry.starts_at < ends_at)
    return db.scalars(query.order_by(ScheduleEntry.starts_at, ScheduleEntry.id)).all()


@router.post("/schedule/{entry_id}/check-in", response_model=EntryOut)
def check_in(entry_id: str, data: CheckIn, request: Request, db: DB, user: CurrentUser):
    with request.app.state.schedule_lock:
        db.execute(
            select(User).where(User.id == user.id).with_for_update()
        ).scalar_one()
        entry = db.get(ScheduleEntry, entry_id)
        if entry is None or entry.user_id != user.id:
            raise HTTPException(404, "Schedule entry not found")
        duration = minutes(entry.starts_at, entry.ends_at)
        actual = (
            data.actual_minutes
            if data.actual_minutes is not None
            else (duration if data.status == "completed" else 0)
        )
        if (
            actual > duration
            or (data.status == "missed" and actual != 0)
            or (data.status == "completed" and actual == 0)
        ):
            raise HTTPException(
                422,
                "Completed minutes must be 1..session duration; missed sessions record 0",
            )
        if entry.status != "planned":
            if entry.status == data.status and entry.actual_minutes == actual:
                return entry
            raise HTTPException(409, "A check-in has already been recorded")
        if entry.starts_at > request.app.state.now():
            raise HTTPException(409, "Check in when the session starts")
        task = db.get(Task, entry.task_id)
        if task.status == "cancelled":
            raise HTTPException(409, "This task is cancelled")
        if task.assignee_id != user.id:
            raise HTTPException(
                409, "This task has been reassigned; refresh your calendar"
            )
        entry.status, entry.actual_minutes = data.status, actual
        task.completed_minutes = min(
            task.duration_minutes, task.completed_minutes + actual
        )
        if task.completed_minutes >= task.duration_minutes:
            task.status = "completed"
            invalidate_future(db, user.id, request.app.state.now(), task.id)
        db.commit()
        return entry


@router.get("/reports/weekly", response_model=ReportOut)
def weekly_report(
    request: Request, db: DB, user: CurrentUser, start_date: date | None = None
):
    local = request.app.state.now().astimezone(ZoneInfo(user.timezone)).date()
    start_date = start_date or local - timedelta(days=local.weekday())
    report = progress_report(db, user, start_date)
    start = datetime.combine(start_date, time.min, ZoneInfo(user.timezone))
    count = db.scalar(
        select(func.count(ReviewLog.id)).where(
            ReviewLog.user_id == user.id,
            ReviewLog.reviewed_at >= start,
            ReviewLog.reviewed_at < start + timedelta(days=7),
        )
    )
    now = request.app.state.now()
    local_now = now.astimezone(ZoneInfo(user.timezone))
    end = start + timedelta(days=7)
    tasks = select(func.count(func.distinct(Task.roadmap_node_id))).where(
        Task.assignee_id == user.id, Task.due_at >= start, Task.due_at < end
    )
    nodes = (
        select(RoadmapNode.id, RoadmapNode.title, RoadmapNode.roadmap_id)
        .join(Roadmap)
        .where(Roadmap.user_id == user.id)
    )
    milestones = nodes.where(
        RoadmapNode.type == "milestone",
        RoadmapNode.due_at >= now,
        RoadmapNode.due_at < now + timedelta(days=7),
    ).order_by(RoadmapNode.due_at)
    reviews = nodes.where(
        RoadmapNode.id.in_(
            select(ReviewCard.node_id).where(
                ReviewCard.user_id == user.id, ReviewCard.due_at <= now
            )
        )
    ).order_by(RoadmapNode.title)
    return {
        **report.model_dump(),
        "review_count": count,
        "completed_nodes": db.scalar(tasks.where(Task.status == "completed")),
        "overdue_nodes": db.scalar(
            tasks.where(
                Task.status.not_in(["completed", "cancelled"]), Task.due_at < now
            )
        ),
        "upcoming_milestones": db.execute(milestones).mappings().all(),
        "review_nodes": db.execute(reviews).mappings().all(),
        "reminder_due": bool(
            user.weekly_reminder and local_now.weekday() == 6 and local_now.hour >= 19
        ),
        "reminder_enabled": bool(user.weekly_reminder),
        "next_week_deadline": end + timedelta(days=7, seconds=-1),
    }


class ReminderStatus(BaseModel):
    reminder_due: bool
    seconds_to_change: int


@router.get("/me/weekly-reminder", response_model=ReminderStatus)
def weekly_reminder(user: CurrentUser, request: Request):
    now = request.app.state.now().astimezone(ZoneInfo(user.timezone))
    sunday = now.date() + timedelta(days=6 - now.weekday())
    at = datetime.combine(sunday, time(19), now.tzinfo)
    due = now >= at
    boundary = (
        datetime.combine(sunday + timedelta(days=1), time.min, now.tzinfo)
        if due
        else at
    )
    return ReminderStatus(
        reminder_due=bool(user.weekly_reminder and due),
        seconds_to_change=max(1, int(boundary.timestamp() - now.timestamp()) + 1),
    )


class LearningPreferences(BaseModel):
    guide_enabled: bool
    weekly_reminder: bool


class PreferenceUpdate(BaseModel):
    guide_enabled: bool | None = None
    weekly_reminder: bool | None = None


@router.get("/me/learning-preferences", response_model=LearningPreferences)
def learning_preferences(user: CurrentUser):
    return LearningPreferences(
        guide_enabled=bool(user.guide_enabled),
        weekly_reminder=bool(user.weekly_reminder),
    )


@router.patch("/me/learning-preferences", response_model=LearningPreferences)
def update_learning_preferences(data: PreferenceUpdate, db: DB, user: CurrentUser):
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, int(value))
    db.commit()
    return learning_preferences(user)


@router.get("/notifications", response_model=list[NotificationOut], tags=["Reminders"])
def notifications(
    request: Request,
    db: DB,
    user: CurrentUser,
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
):
    valid_entries = select(ScheduleEntry.id).where(ScheduleEntry.status == "planned")
    query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.created_at <= request.app.state.now(),
        (Notification.entry_id.is_(None)) | (Notification.entry_id.in_(valid_entries)),
    )
    if unread_only:
        query = query.where(Notification.read.is_(False))
    return db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id).limit(limit)
    ).all()


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationOut,
    tags=["Reminders"],
)
def read_notification(notification_id: str, db: DB, user: CurrentUser):
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    row.read = True
    db.commit()
    return row
