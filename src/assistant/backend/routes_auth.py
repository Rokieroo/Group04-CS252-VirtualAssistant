"""Account, profile and session lifecycle."""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.companion import girlfriend_mode_allowed

from .dependencies import DB, CurrentUser
from .models import AuthSession, User
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
    user = User(
        email=data.email,
        name=data.name,
        timezone=data.timezone,
        birth_year=data.birth_year,
        account_level=data.account_level,
        password_hash=hash_password(data.password),
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
