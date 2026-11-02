"""Companion chat with private, persisted per-user history."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select

from app.companion import companion_mode

from .dependencies import DB, CurrentUser
from .models import ChatMessage
from .schemas import ChatOut, ChatRequest, MessageOut
from .services import companion_reply

router = APIRouter(prefix="/ai", tags=["AI companion"])


CHAT_PER_MINUTE = 10


@router.post(
    "/chat",
    response_model=ChatOut,
    responses={429: {"description": "Chat rate limit reached"}},
)
def chat(data: ChatRequest, request: Request, db: DB, user: CurrentUser):
    now = request.app.state.now()
    if companion_mode(user, now.date()) == "off":
        raise HTTPException(403, "The companion is turned off in your profile")
    # Counted from stored messages, so the limit holds across workers; each call may
    # hit the paid LLM. Concurrent bursts can overshoot by a few requests.
    recent = db.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(
            ChatMessage.user_id == user.id,
            ChatMessage.role == "user",
            ChatMessage.created_at > now - timedelta(minutes=1),
        )
    )
    if recent >= CHAT_PER_MINUTE:
        raise HTTPException(
            429, "You are sending messages too fast", headers={"Retry-After": "60"}
        )
    return companion_reply(db, user, data, request.app.state.companion, now)


@router.get("/messages", response_model=list[MessageOut])
def history(db: DB, user: CurrentUser, limit: int = Query(default=50, ge=1, le=200)):
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


@router.delete("/messages", status_code=204)
def clear_history(db: DB, user: CurrentUser):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.commit()
    return Response(status_code=204)
