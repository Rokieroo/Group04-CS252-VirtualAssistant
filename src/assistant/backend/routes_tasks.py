"""Personal goals and personal/team tasks (UC-01)."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import delete, or_, select

from .dependencies import DB, CurrentUser
from .models import Goal, Membership, ScheduleEntry, Task
from .schemas import GoalCreate, GoalOut, GoalPatch, TaskCreate, TaskOut, TaskPatch
from .services import (
    invalidate_future,
    lock_task_for_edit,
    owned_goal,
    serialize_schedule_changes,
    team_member,
    visible_task,
)

router = APIRouter(tags=["Goals and tasks"])


@router.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(data: GoalCreate, db: DB, user: CurrentUser):
    goal = Goal(owner_id=user.id, **data.model_dump())
    db.add(goal)
    db.commit()
    return goal


@router.get("/goals", response_model=list[GoalOut])
def list_goals(db: DB, user: CurrentUser):
    return db.scalars(
        select(Goal).where(Goal.owner_id == user.id).order_by(Goal.created_at, Goal.id)
    ).all()


@router.get("/goals/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: str, db: DB, user: CurrentUser):
    return owned_goal(db, goal_id, user.id)


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: str, data: GoalPatch, db: DB, user: CurrentUser):
    goal = owned_goal(db, goal_id, user.id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(goal, key, value)
    db.commit()
    return goal


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: str, db: DB, user: CurrentUser):
    db.delete(owned_goal(db, goal_id, user.id))
    db.commit()
    return Response(status_code=204)


@router.post("/tasks", response_model=TaskOut, status_code=201)
@serialize_schedule_changes
def create_task(data: TaskCreate, request: Request, db: DB, user: CurrentUser):
    if data.due_at <= request.app.state.now():
        raise HTTPException(422, "due_at must be in the future")
    assignee = data.assignee_id or user.id
    if data.team_id is not None:
        team_member(db, data.team_id, user.id)
        team_member(db, data.team_id, assignee)
        if data.goal_id is not None:
            raise HTTPException(422, "A team task cannot expose a personal goal")
    elif assignee != user.id:
        raise HTTPException(
            422, "Use a team workspace to assign a task to someone else"
        )
    if data.goal_id is not None:
        owned_goal(db, data.goal_id, user.id)
    task = Task(owner_id=user.id, **{**data.model_dump(), "assignee_id": assignee})
    db.add(task)
    db.commit()
    return task


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    db: DB,
    user: CurrentUser,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    team_id: str | None = None,
    status: str | None = Query(default=None, pattern="^(pending|completed|cancelled)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    teams = select(Membership.team_id).where(Membership.user_id == user.id)
    query = select(Task).where(or_(Task.owner_id == user.id, Task.team_id.in_(teams)))
    if team_id is not None:
        team_member(db, team_id, user.id)
        query = query.where(Task.team_id == team_id)
    if on_date is not None:
        start = datetime.combine(on_date, time.min, ZoneInfo(user.timezone))
        end = start + timedelta(days=1)
        scheduled_ids = select(ScheduleEntry.task_id).where(
            ScheduleEntry.starts_at < end, ScheduleEntry.ends_at > start
        )
        query = query.where(
            or_(
                (Task.due_at >= start) & (Task.due_at < end), Task.id.in_(scheduled_ids)
            )
        )
    if status is not None:
        query = query.where(Task.status == status)
    return db.scalars(
        query.order_by(Task.priority, Task.due_at, Task.id).offset(offset).limit(limit)
    ).all()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: DB, user: CurrentUser):
    return visible_task(db, task_id, user.id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
@serialize_schedule_changes
def update_task(
    task_id: str, data: TaskPatch, request: Request, db: DB, user: CurrentUser
):
    task = lock_task_for_edit(db, task_id, user.id)
    changes = data.model_dump(exclude_unset=True)
    if data.goal_id is not None:
        if task.team_id is not None:
            raise HTTPException(422, "Team tasks cannot reference personal goals")
        owned_goal(db, data.goal_id, user.id)
    if data.due_at is not None and data.due_at <= request.app.state.now():
        raise HTTPException(422, "due_at must be in the future")
    if (
        data.duration_minutes is not None
        and data.duration_minutes < task.completed_minutes
    ):
        raise HTTPException(
            422, "Duration cannot be less than recorded completed minutes"
        )
    if task.status == "completed" and changes.keys() & {"duration_minutes", "status"}:
        raise HTTPException(
            409, "Completed tasks retain their check-in history; create a new task"
        )
    if changes.keys() & {"duration_minutes", "priority", "due_at", "status"}:
        if data.status == "cancelled":
            db.execute(
                delete(ScheduleEntry).where(
                    ScheduleEntry.task_id == task.id, ScheduleEntry.status == "planned"
                )
            )
        else:
            invalidate_future(db, task.assignee_id, request.app.state.now(), task.id)
    for key, value in changes.items():
        setattr(task, key, value)
    if task.completed_minutes == task.duration_minutes:
        task.status = "completed"
    db.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=204)
@serialize_schedule_changes
def delete_task(task_id: str, request: Request, db: DB, user: CurrentUser):
    task = lock_task_for_edit(db, task_id, user.id)
    if task.completed_minutes or db.scalar(
        select(ScheduleEntry.id)
        .where(ScheduleEntry.task_id == task.id, ScheduleEntry.status != "planned")
        .limit(1)
    ):
        raise HTTPException(
            409, "Tasks with check-in history must be cancelled instead of deleted"
        )
    db.execute(delete(ScheduleEntry).where(ScheduleEntry.task_id == task.id))
    db.delete(task)
    db.commit()
    return Response(status_code=204)
