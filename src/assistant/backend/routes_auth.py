"""Account, profile and session lifecycle."""

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.companion import girlfriend_mode_allowed

from .catalog_models import RoadmapEdge
from .dependencies import DB, CurrentUser
from .models import (
    AuthSession,
    Availability,
    BusyBlock,
    ChatMessage,
    Course,
    Goal,
    Job,
    Membership,
    Notification,
    Recommendation,
    RecommendationEvent,
    ResourceFeedback,
    ReviewCard,
    ReviewLog,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Source,
    Task,
    Team,
    User,
)
from .schemas import Login, ProfilePatch, Register, TokenOut, UserOut
from .security import hash_password, token_hash, verify_password

router = APIRouter(tags=["Accounts"])
logger = logging.getLogger(__name__)
_dummy_hash = hash_password("unregistered-account-placeholder")
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


def issue_session(db, user, request):
    raw = secrets.token_urlsafe(32)
    now = request.app.state.now()
    expires = now + timedelta(minutes=request.app.state.settings.session_minutes)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.add(AuthSession(token_hash=token_hash(raw), user_id=user.id, expires_at=expires))
    db.commit()
    return TokenOut(
        access_token=raw, expires_at=expires, user=UserOut.model_validate(user)
    )


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: Register, request: Request, db: DB):
    now = request.app.state.now()
    is_under_18 = (now.year - data.birth_year < 18)
    if is_under_18 and not data.parental_consent:
        raise HTTPException(422, "Parental consent is required for learners under 18")

    user = User(
        email=data.email,
        name=data.name,
        timezone=data.timezone,
        birth_year=data.birth_year,
        account_level=data.account_level,
        password_hash=hash_password(data.password),
        parental_consent=1 if data.parental_consent else 0,
        parental_consent_at=now.isoformat() if data.parental_consent else None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None
    return issue_session(db, user, request)


@router.post(
    "/auth/login",
    response_model=TokenOut,
    responses={429: {"description": "Too many failed attempts; retry later"}},
)
def login(data: Login, request: Request, db: DB):
    now = request.app.state.now()
    # Row lock: concurrent wrong guesses cannot all slip under the limit.
    user = db.scalar(select(User).where(User.email == data.email).with_for_update())
    if user is not None and user.locked_until:
        locked_until = datetime.fromisoformat(user.locked_until)
        if locked_until > now:
            logger.info("login user_id=%s result=locked", user.id)
            raise HTTPException(
                429,
                "Too many failed attempts. Try again later.",
                headers={"Retry-After": str(int((locked_until - now).total_seconds()))},
            )
    valid = verify_password(data.password, user.password_hash if user else _dummy_hash)
    if user is None or not valid:
        if user is not None:
            # shortcut: counts consecutive failures since the last success, not a
            # sliding 15-minute window; add a failure timestamp column if that matters.
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                user.failed_login_attempts = 0
                user.locked_until = (now + LOCKOUT).isoformat()
            db.commit()
        logger.info(
            "login user_id=%s result=invalid", user.id if user else "unknown"
        )
        raise HTTPException(401, "Invalid email or password")
    user.failed_login_attempts, user.locked_until = 0, None
    logger.info("login user_id=%s result=ok", user.id)
    return issue_session(db, user, request)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DB, user: CurrentUser):
    raw = request.headers["authorization"].split()[1]
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(raw)))
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def profile(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(data: ProfilePatch, request: Request, user: CurrentUser, db: DB):
    changes = data.model_dump(exclude_unset=True)
    if changes.get("companion_mode") == "girlfriend" and not girlfriend_mode_allowed(
        user, request.app.state.now().date()
    ):
        raise HTTPException(403, "This companion mode needs a verified adult account")
    for key, value in changes.items():
        setattr(user, key, value)
    db.commit()
    return user


@router.get("/me/export")
def export_user_data(user: CurrentUser, db: DB, request: Request):
    """Export complete personal data in JSON format (Issue #164, GDPR/Child Safety)."""
    user_id = user.id

    profile_data = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "account_level": user.account_level,
        "birth_year": user.birth_year,
        "companion_mode": user.companion_mode,
        "adult_verified": bool(user.adult_verified),
        "parental_consent": bool(user.parental_consent),
        "parental_consent_at": user.parental_consent_at,
        "timezone": user.timezone,
        "personality": user.personality,
        "created_at": str(user.created_at),
    }

    courses = db.scalars(select(Course).where(Course.owner_id == user_id)).all()
    courses_data = [
        {
            "id": c.id,
            "title": c.title,
            "level": c.level,
            "created_at": str(c.created_at),
        }
        for c in courses
    ]

    roadmaps = db.scalars(select(Roadmap).where(Roadmap.user_id == user_id)).all()
    roadmap_ids = [r.id for r in roadmaps]
    nodes_by_roadmap: dict[str, list[RoadmapNode]] = defaultdict(list)
    edges_by_roadmap: dict[str, list[RoadmapEdge]] = defaultdict(list)
    if roadmap_ids:
        for node in db.scalars(
            select(RoadmapNode).where(RoadmapNode.roadmap_id.in_(roadmap_ids))
        ):
            nodes_by_roadmap[node.roadmap_id].append(node)
        for edge in db.scalars(
            select(RoadmapEdge).where(RoadmapEdge.roadmap_id.in_(roadmap_ids))
        ):
            edges_by_roadmap[edge.roadmap_id].append(edge)

    roadmaps_data = [
        {
            "id": r.id,
            "course_id": r.course_id,
            "title": r.title,
            "nodes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "type": getattr(n, "type", ""),
                    "week": n.week,
                    "due_at": str(n.due_at) if n.due_at else None,
                    "duration_minutes": getattr(n, "duration_minutes", None),
                }
                for n in nodes_by_roadmap[r.id]
            ],
            "edges": [
                {"parent_id": e.parent_id, "child_id": e.child_id}
                for e in edges_by_roadmap[r.id]
            ],
        }
        for r in roadmaps
    ]

    tasks = db.scalars(
        select(Task).where((Task.owner_id == user_id) | (Task.assignee_id == user_id))
    ).all()
    tasks_data = [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "due_at": str(t.due_at) if t.due_at else None,
            "duration_minutes": t.duration_minutes,
            "completed_minutes": t.completed_minutes,
            "roadmap_node_id": t.roadmap_node_id,
        }
        for t in tasks
    ]

    schedule_entries = db.scalars(
        select(ScheduleEntry).where(ScheduleEntry.user_id == user_id)
    ).all()
    schedule_data = [
        {
            "id": s.id,
            "task_id": s.task_id,
            "starts_at": str(s.starts_at),
            "ends_at": str(s.ends_at),
            "status": s.status,
        }
        for s in schedule_entries
    ]

    chat_messages = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user_id).order_by(ChatMessage.created_at)
    ).all()
    chat_data = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": str(m.created_at),
            "safety_flag": bool(m.safety_flag),
        }
        for m in chat_messages
    ]

    course_ids = [c.id for c in courses]
    sources = (
        db.scalars(select(Source).where(Source.course_id.in_(course_ids))).all()
        if course_ids
        else []
    )
    sources_data = [
        {
            "id": s.id,
            "course_id": s.course_id,
            "file_name": s.file_name,
            "page": s.page,
            "kind": getattr(s, "kind", ""),
        }
        for s in sources
    ]

    notifications = db.scalars(
        select(Notification).where(Notification.user_id == user_id)
    ).all()
    notifications_data = [
        {
            "id": n.id,
            "title": n.title,
            "read_at": str(n.read_at) if n.read_at else None,
            "created_at": str(n.created_at),
        }
        for n in notifications
    ]

    feedback = db.scalars(
        select(ResourceFeedback).where(ResourceFeedback.user_id == user_id)
    ).all()
    feedback_data = [
        {
            "id": f.id,
            "resource_id": f.resource_id,
            "rating": f.rating,
            "comment": f.comment,
        }
        for f in feedback
    ]

    goals = db.scalars(select(Goal).where(Goal.owner_id == user_id)).all()
    goals_data = [
        {
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "due_at": str(g.due_at) if g.due_at else None,
        }
        for g in goals
    ]

    review_cards = db.scalars(
        select(ReviewCard).where(ReviewCard.user_id == user_id)
    ).all()
    review_cards_data = [
        {
            "item_id": rc.item_id,
            "node_id": rc.node_id,
            "due_at": str(rc.due_at),
            "stability": rc.stability,
            "difficulty": rc.difficulty,
            "state": rc.state,
            "step": rc.step,
            "last_review": str(rc.last_review) if rc.last_review else None,
        }
        for rc in review_cards
    ]

    review_logs = db.scalars(
        select(ReviewLog)
        .where(ReviewLog.user_id == user_id)
        .order_by(ReviewLog.reviewed_at)
    ).all()
    review_logs_data = [
        {
            "id": rl.id,
            "item_id": rl.item_id,
            "node_id": rl.node_id,
            "rating": rl.rating,
            "reviewed_at": str(rl.reviewed_at),
            "elapsed_days": rl.elapsed_days,
            "scheduled_days": rl.scheduled_days,
        }
        for rl in review_logs
    ]

    return {
        "exported_at": request.app.state.now().isoformat(),
        "user": profile_data,
        "courses": courses_data,
        "roadmaps": roadmaps_data,
        "goals": goals_data,
        "tasks": tasks_data,
        "schedule_entries": schedule_data,
        "chat_messages": chat_data,
        "sources": sources_data,
        "notifications": notifications_data,
        "resource_feedback": feedback_data,
        "review_cards": review_cards_data,
        "review_logs": review_logs_data,
    }


@router.delete("/me", status_code=204)
async def delete_account(
    request: Request,
    user: CurrentUser,
    db: DB,
    confirm: bool = False,
):
    """Hard-delete current user and all related records with explicit confirmation."""
    confirmed = confirm
    if not confirmed:
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("confirm") is True:
                confirmed = True
        except (ValueError, TypeError):
            logger.debug("No JSON body provided for account deletion confirmation")

    if not confirmed:
        raise HTTPException(
            400,
            "Confirmation required to permanently delete account. Pass ?confirm=true or JSON body {'confirm': true}.",
        )

    user_id = user.id

    db.execute(delete(ResourceFeedback).where(ResourceFeedback.user_id == user_id))
    db.execute(
        delete(RecommendationEvent).where(
            RecommendationEvent.recommendation_id.in_(
                select(Recommendation.id).where(Recommendation.user_id == user_id)
            )
        )
    )
    db.execute(delete(Recommendation).where(Recommendation.user_id == user_id))
    db.execute(delete(ReviewLog).where(ReviewLog.user_id == user_id))
    db.execute(delete(ReviewCard).where(ReviewCard.user_id == user_id))

    owned_team_ids = select(Team.id).where(Team.owner_id == user_id)
    db.execute(delete(ScheduleEntry).where(ScheduleEntry.user_id == user_id))
    db.execute(
        delete(Task).where((Task.owner_id == user_id) | (Task.assignee_id == user_id))
    )
    # Other members' tasks in a team this user owned are their data: keep them, drop the team.
    db.execute(
        update(Task).where(Task.team_id.in_(owned_team_ids)).values(team_id=None)
    )
    db.execute(delete(Membership).where(Membership.user_id == user_id))
    db.execute(delete(Team).where(Team.owner_id == user_id))
    db.execute(delete(Goal).where(Goal.owner_id == user_id))
    db.execute(delete(Availability).where(Availability.user_id == user_id))
    db.execute(delete(BusyBlock).where(BusyBlock.user_id == user_id))
    db.execute(delete(Job).where(Job.user_id == user_id))
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
    db.execute(delete(Notification).where(Notification.user_id == user_id))
    db.execute(delete(Roadmap).where(Roadmap.user_id == user_id))
    db.execute(delete(Course).where(Course.owner_id == user_id))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()

    return Response(status_code=204)
