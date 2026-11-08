"""Invitation-based workspaces, task sharing and common free time (UC-09..11)."""

import hmac
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.planner import intersect, minutes, subtract

from .dependencies import DB, CurrentUser
from .models import (
    Availability,
    BusyBlock,
    Invitation,
    Membership,
    ScheduleEntry,
    Task,
    Team,
    User,
)
from .schemas import (
    CommonSlot,
    CoordinateRequest,
    InvitationAccept,
    InvitationCreated,
    InvitationOut,
    InviteCreate,
    MemberOut,
    ShareTask,
    TaskOut,
    TeamCreate,
    TeamOut,
)
from .security import token_hash
from .services import (
    lock_task_for_edit,
    serialize_schedule_changes,
    team_member,
    visible_task,
)

router = APIRouter(tags=["Team workspaces"])


@router.post("/teams", response_model=TeamOut, status_code=201)
def create_team(data: TeamCreate, db: DB, user: CurrentUser):
    team = Team(owner_id=user.id, name=data.name)
    db.add(team)
    db.flush()
    db.add(Membership(team_id=team.id, user_id=user.id))
    db.commit()
    return team


@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: DB, user: CurrentUser):
    return db.scalars(
        select(Team)
        .join(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Team.created_at, Team.id)
    ).all()


@router.get("/teams/{team_id}/members", response_model=list[MemberOut])
def members(team_id: str, db: DB, user: CurrentUser):
    team_member(db, team_id, user.id)
    return db.scalars(
        select(User)
        .join(Membership)
        .where(Membership.team_id == team_id)
        .order_by(User.name, User.id)
    ).all()


@router.post(
    "/teams/{team_id}/invitations", response_model=InvitationCreated, status_code=201
)
def invite(team_id: str, data: InviteCreate, db: DB, user: CurrentUser):
    team = team_member(db, team_id, user.id)
    if team.owner_id != user.id:
        raise HTTPException(403, "Only the workspace owner can invite members")
    existing_user = db.scalar(select(User).where(User.email == data.email))
    if existing_user is not None and db.get(Membership, (team_id, existing_user.id)):
        raise HTTPException(409, "This account is already a member")
    code = secrets.token_urlsafe(12)
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.team_id == team_id, Invitation.email == data.email
        )
    )
    if invitation is None:
        invitation = Invitation(team_id=team_id, email=data.email)
        db.add(invitation)
    # Re-inviting rotates the code, so the owner can always resend a working one.
    invitation.token_hash = token_hash(code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An invitation already exists") from None
    return InvitationCreated(
        **InvitationOut.model_validate(invitation).model_dump(), code=code
    )


@router.get("/invitations", response_model=list[InvitationOut])
def invitations(db: DB, user: CurrentUser):
    return db.scalars(
        select(Invitation).where(
            Invitation.email == user.email, Invitation.accepted.is_(False)
        )
    ).all()


@router.post("/invitations/{invitation_id}/accept", response_model=TeamOut)
def accept(
    invitation_id: str, data: InvitationAccept, db: DB, user: CurrentUser
):
    invitation = db.scalar(
        select(Invitation).where(Invitation.id == invitation_id).with_for_update()
    )
    # Emails are not verified, so the matching email alone proves nothing: anyone
    # could register an invitee's address first. The out-of-band code is required.
    if (
        invitation is None
        or invitation.email != user.email
        or not hmac.compare_digest(invitation.token_hash, token_hash(data.code))
    ):
        raise HTTPException(404, "Invitation not found")
    if not db.get(Membership, (invitation.team_id, user.id)):
        db.add(Membership(team_id=invitation.team_id, user_id=user.id))
    invitation.accepted = True
    db.commit()
    return db.get(Team, invitation.team_id)


@router.delete("/teams/{team_id}/members/{member_id}", status_code=204)
@serialize_schedule_changes
def remove_member(
    team_id: str, member_id: str, request: Request, db: DB, user: CurrentUser
):
    team = team_member(db, team_id, user.id)
    if user.id not in {member_id, team.owner_id}:
        raise HTTPException(403, "Only the owner can remove other members")
    if member_id == team.owner_id:
        raise HTTPException(409, "The owner cannot leave their own workspace")
    membership = db.get(Membership, (team_id, member_id))
    if membership is None:
        raise HTTPException(404, "Member not found")
    for locked_id in sorted({member_id, team.owner_id}):
        db.execute(select(User).where(User.id == locked_id).with_for_update()).one()
    # Their open team work moves to the owner; unchecked sessions leave their calendar.
    pending = (
        Task.team_id == team_id,
        Task.assignee_id == member_id,
        Task.status == "pending",
    )
    db.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.task_id.in_(select(Task.id).where(*pending)),
            ScheduleEntry.status == "planned",
        )
    )
    db.execute(update(Task).where(*pending).values(assignee_id=team.owner_id))
    db.delete(membership)
    db.commit()
    return Response(status_code=204)


@router.post("/tasks/{task_id}/share", response_model=TaskOut)
@serialize_schedule_changes
def share(task_id: str, data: ShareTask, request: Request, db: DB, user: CurrentUser):
    task = visible_task(db, task_id, user.id, edit=True)
    if task.owner_id != user.id:
        raise HTTPException(403, "Only the task creator can share or reassign it")
    team_member(db, data.team_id, user.id)
    assignee = data.assignee_id or user.id
    team_member(db, data.team_id, assignee)
    task = lock_task_for_edit(db, task_id, user.id, extra_assignees=(assignee,))
    if task.completed_minutes or db.scalar(
        select(ScheduleEntry.id)
        .where(ScheduleEntry.task_id == task.id, ScheduleEntry.status != "planned")
        .limit(1)
    ):
        raise HTTPException(
            409, "A task with check-in history cannot be moved to another schedule"
        )
    # Unchecked sessions, including past ones, belong to the old assignee.
    db.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.task_id == task.id, ScheduleEntry.status == "planned"
        )
    )
    task.team_id, task.assignee_id, task.goal_id = data.team_id, assignee, None
    db.commit()
    return task


@router.post("/teams/{team_id}/coordinate", response_model=list[CommonSlot])
def coordinate(team_id: str, data: CoordinateRequest, db: DB, user: CurrentUser):
    team_member(db, team_id, user.id)
    member_ids = list(
        db.scalars(select(Membership.user_id).where(Membership.team_id == team_id))
    )
    common = [(data.starts_at, data.ends_at)]
    for member_id in member_ids:
        windows = db.scalars(
            select(Availability).where(Availability.user_id == member_id)
        ).all()
        busy = db.scalars(select(BusyBlock).where(BusyBlock.user_id == member_id)).all()
        scheduled = db.scalars(
            select(ScheduleEntry).where(
                ScheduleEntry.user_id == member_id,
                ScheduleEntry.status != "missed",
                ScheduleEntry.starts_at < data.ends_at,
                ScheduleEntry.ends_at > data.starts_at,
            )
        ).all()
        free = subtract(
            [(window.starts_at, window.ends_at) for window in windows],
            [(block.starts_at, block.ends_at) for block in busy]
            + [(entry.starts_at, entry.ends_at) for entry in scheduled],
        )
        common = intersect(common, free)
        if not common:
            break
    return [
        CommonSlot(starts_at=start, ends_at=end)
        for start, end in common
        if minutes(start, end) >= data.duration_minutes
    ][:100]
