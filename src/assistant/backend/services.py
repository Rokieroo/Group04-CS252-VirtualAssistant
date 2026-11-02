"""Database transactions and ownership rules shared by the API routes.

Each function loads rows, hands plain values to the pure parts in app/ and writes
the result back; the decisions themselves live in app/ (ADR 003).
"""

from datetime import datetime, time, timedelta
from functools import wraps
from inspect import signature
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.companion import (
    Companion,
    CompanionContext,
    NextSession,
    PendingTask,
    companion_mode,
)
from app.planner import WorkItem, build_plan, minutes
from app.roadmap import task_due_at

from .models import (
    Availability,
    BusyBlock,
    ChatMessage,
    Goal,
    Membership,
    Notification,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Task,
    Team,
    User,
)
from .schemas import ChatOut, ChatRequest, PlanOut, PlanRequest, ReportOut, Unscheduled

REMINDER_LEAD = timedelta(minutes=15)
ROADMAP_SESSION_MINUTES = (25, 50)  # spec 10.3.4
MAX_PLAN_HORIZON = timedelta(days=90)  # PlanRequest's limit


def serialize_schedule_changes(handler):
    """SQLite has no row locks; share the planner lock across related mutations."""
    parameters = signature(handler)

    @wraps(handler)
    def serialized(*args, **kwargs):
        arguments = parameters.bind(*args, **kwargs).arguments
        with arguments["request"].app.state.schedule_lock:
            try:
                return handler(*args, **kwargs)
            except Exception:
                arguments["db"].rollback()
                raise

    return serialized


def owned_goal(db: Session, goal_id: str, user_id: str):
    goal = db.get(Goal, goal_id)
    if goal is None or goal.owner_id != user_id:
        raise HTTPException(404, "Goal not found")
    return goal


def team_member(db: Session, team_id: str, user_id: str):
    team = db.get(Team, team_id)
    if team is None or db.get(Membership, (team_id, user_id)) is None:
        raise HTTPException(404, "Team not found")
    return team


def visible_task(db: Session, task_id: str, user_id: str, edit=False):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.team_id is not None:
        team = team_member(db, task.team_id, user_id)
        if edit and user_id not in {task.owner_id, task.assignee_id, team.owner_id}:
            raise HTTPException(
                403, "Only the creator, assignee or team owner can edit this task"
            )
    elif task.owner_id != user_id:
        raise HTTPException(404, "Task not found")
    return task


def lock_task_for_edit(db: Session, task_id: str, user_id: str, extra_assignees=()):
    task = visible_task(db, task_id, user_id, edit=True)
    original_assignee = task.assignee_id
    for assignee_id in sorted({original_assignee, *extra_assignees}):
        db.execute(
            select(User).where(User.id == assignee_id).with_for_update()
        ).scalar_one()
    current = db.scalar(
        select(Task).where(Task.id == task_id).execution_options(populate_existing=True)
    )
    if current is None:
        raise HTTPException(404, "Task not found")
    if current.assignee_id != original_assignee:
        raise HTTPException(409, "The task was reassigned; refresh and try again")
    return visible_task(db, task_id, user_id, edit=True)


def invalidate_future(
    db: Session, user_id: str, now: datetime, task_id: str | None = None
):
    query = delete(ScheduleEntry).where(
        ScheduleEntry.user_id == user_id,
        ScheduleEntry.status == "planned",
        ScheduleEntry.starts_at >= now,
    )
    if task_id is not None:
        query = query.where(ScheduleEntry.task_id == task_id)
    db.execute(query)


def make_plan(db: Session, user: User, data: PlanRequest, now: datetime):
    # PostgreSQL serializes plans, check-ins and task edits on the same user row.
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    windows = db.scalars(
        select(Availability).where(Availability.user_id == user.id)
    ).all()
    busy = db.scalars(select(BusyBlock).where(BusyBlock.user_id == user.id)).all()
    all_entries = db.scalars(
        select(ScheduleEntry).where(ScheduleEntry.user_id == user.id)
    ).all()
    expired_ids = {
        entry.id
        for entry in all_entries
        if entry.status == "planned" and entry.ends_at <= now
    }
    replaceable = [
        entry
        for entry in all_entries
        if (
            entry.status == "planned"
            and entry.starts_at >= data.starts_at
            and entry.ends_at <= data.ends_at
        )
    ]
    replaceable_ids = {entry.id for entry in replaceable}
    fixed = [
        entry
        for entry in all_entries
        if entry.id not in replaceable_ids | expired_ids and entry.status != "missed"
    ]
    planned_elsewhere: dict[str, int] = {}
    for entry in fixed:
        if entry.status == "planned":
            planned_elsewhere[entry.task_id] = planned_elsewhere.get(
                entry.task_id, 0
            ) + minutes(entry.starts_at, entry.ends_at)
    tasks = db.scalars(
        select(Task).where(Task.assignee_id == user.id, Task.status == "pending")
    ).all()
    proposal = build_plan(
        [
            WorkItem(
                task.id,
                max(
                    0,
                    task.duration_minutes
                    - task.completed_minutes
                    - planned_elsewhere.get(task.id, 0),
                ),
                task.priority,
                task.due_at,
            )
            for task in tasks
        ],
        [(window.starts_at, window.ends_at) for window in windows],
        [(block.starts_at, block.ends_at) for block in busy]
        + [(entry.starts_at, entry.ends_at) for entry in fixed],
        [(entry.starts_at, entry.ends_at) for entry in fixed],
        data,
        user.timezone,
    )
    plan = PlanOut.model_validate(
        {
            "committed": False,
            "expired_sessions": len(expired_ids),
            "entries": proposal.entries,
            "unscheduled": proposal.unscheduled,
        },
        from_attributes=True,
    )
    if data.commit:
        if expired_ids:
            db.execute(
                update(ScheduleEntry)
                .where(ScheduleEntry.id.in_(expired_ids))
                .values(status="missed", actual_minutes=0)
            )
        if replaceable_ids:
            db.execute(
                delete(ScheduleEntry).where(ScheduleEntry.id.in_(replaceable_ids))
            )
        rows = [
            ScheduleEntry(
                user_id=user.id,
                task_id=entry.task_id,
                starts_at=entry.starts_at,
                ends_at=entry.ends_at,
            )
            for entry in plan.entries
        ]
        db.add_all(rows)
        db.flush()
        titles = {task.id: task.title for task in tasks}
        zone = ZoneInfo(user.timezone)
        # Reminders are written now and become visible (created_at) 15 minutes before
        # the session, so reading notifications never writes. Deleting or replanning
        # a session removes its reminder through the ON DELETE CASCADE foreign key.
        db.add_all(
            Notification(
                user_id=user.id,
                entry_id=row.id,
                created_at=row.starts_at - REMINDER_LEAD,
                message=f"{titles[row.task_id]} starts at "
                f"{row.starts_at.astimezone(zone):%H:%M} ({user.timezone}).",
            )
            for row in rows
        )
        db.add(
            Notification(
                user_id=user.id,
                created_at=now,
                message="Your schedule has been updated. Review the new plan.",
            )
        )
        db.commit()
        plan.committed = True
    return plan


def schedule_roadmap(
    db: Session,
    user: User,
    roadmap: Roadmap,
    nodes: list[RoadmapNode],
    max_daily_minutes: int,
    starts_at: datetime | None,
    now: datetime,
) -> tuple[list[Task], list[ScheduleEntry], list[Unscheduled]]:
    """Give each node one task (reused on later calls), then plan through make_plan so
    sessions fit availability minus busy blocks and existing sessions (spec 10.4)."""
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

    start = max(starts_at or now, now)
    if start.second or start.microsecond:
        start = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    latest_due = max(task.due_at for task in tasks).replace(second=0, microsecond=0)
    shortest, longest = ROADMAP_SESSION_MINUTES
    request = PlanRequest(
        starts_at=start,
        ends_at=min(start + MAX_PLAN_HORIZON, max(latest_due, start + timedelta(days=1))),
        min_session_minutes=shortest,
        max_session_minutes=longest,
        daily_limit_minutes=max_daily_minutes,
        commit=True,
    )
    plan = make_plan(db, user, request, now)
    task_ids = {task.id for task in tasks}
    sessions = db.scalars(
        select(ScheduleEntry)
        .where(ScheduleEntry.task_id.in_(task_ids), ScheduleEntry.status == "planned")
        .order_by(ScheduleEntry.starts_at)
    ).all()
    return tasks, list(sessions), [i for i in plan.unscheduled if i.task_id in task_ids]


def progress_report(db: Session, user: User, start_date):
    cache = db.info.get("report_cache")
    cache_key = (user.id, user.timezone, start_date)
    generation = cache.generation if cache is not None else None
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(start_date, time.min, zone)
    end = start + timedelta(days=7)
    tasks = db.scalars(
        select(Task).where(
            Task.assignee_id == user.id,
            Task.status != "cancelled",
            Task.due_at >= start,
            Task.due_at < end,
        )
    ).all()
    entries = db.scalars(
        select(ScheduleEntry).where(
            ScheduleEntry.user_id == user.id,
            ScheduleEntry.starts_at < end,
            ScheduleEntry.ends_at > start,
        )
    ).all()
    # Missed sessions are counted in missed_sessions; their replanned copies would
    # otherwise count the same work twice.
    planned = sum(
        minutes(max(entry.starts_at, start), min(entry.ends_at, end))
        for entry in entries
        if entry.status != "missed"
    )
    completed = sum(
        entry.actual_minutes
        for entry in entries
        if entry.status == "completed" and start <= entry.starts_at < end
    )
    total = len(tasks)
    done = sum(task.status == "completed" for task in tasks)
    report = ReportOut(
        start_date=start_date,
        end_date=start_date + timedelta(days=6),
        total_tasks=total,
        completed_tasks=done,
        planned_minutes=planned,
        completed_minutes=completed,
        missed_sessions=sum(entry.status == "missed" for entry in entries),
        completion_percent=round(done * 100 / total) if total else 0,
    )
    if cache is not None:
        cache.put(cache_key, report, generation)
    return report


def companion_reply(
    db: Session,
    user: User,
    data: ChatRequest,
    companion: Companion,
    now: datetime,
) -> ChatOut:
    """One chat turn: gather read-only facts, ask the companion, store both messages."""
    local_date = now.astimezone(ZoneInfo(user.timezone)).date()
    report = progress_report(
        db, user, local_date - timedelta(days=local_date.weekday())
    )
    tasks = db.scalars(
        select(Task)
        .where(Task.assignee_id == user.id, Task.status == "pending")
        .order_by(Task.priority, Task.due_at, Task.id)
        .limit(5)
    ).all()
    next_entry = db.scalar(
        select(ScheduleEntry)
        .where(
            ScheduleEntry.user_id == user.id,
            ScheduleEntry.status == "planned",
            ScheduleEntry.ends_at > now,
        )
        .order_by(ScheduleEntry.starts_at)
        .limit(1)
    )
    history = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(10)
    ).all()
    context = CompanionContext(
        name=user.name,
        timezone=user.timezone,
        mood=data.mood,
        mode=companion_mode(user, now.date()),
        personality=user.personality,
        weekly_progress=report.model_dump(mode="json"),
        pending_tasks=[
            PendingTask(
                task.title, task.due_at, task.duration_minutes - task.completed_minutes
            )
            for task in tasks
        ],
        next_session=NextSession(
            db.get(Task, next_entry.task_id).title, next_entry.starts_at
        )
        if next_entry
        else None,
        history=[(row.role, row.content) for row in reversed(history)],
    )
    reply = companion.reply(context, data.message)
    db.add(
        ChatMessage(user_id=user.id, role="user", content=data.message, created_at=now)
    )
    db.add(
        ChatMessage(
            user_id=user.id,
            role="assistant",
            content=reply.text,
            created_at=now + timedelta(microseconds=1),
        )
    )
    db.commit()
    return ChatOut(
        reply=reply.text,
        provider=reply.provider,
        fallback_reason=reply.fallback_reason,
    )
