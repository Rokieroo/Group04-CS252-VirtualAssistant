"""Request-scoped database session and authenticated identity."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuthSession, User
from .security import token_hash

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    with request.app.state.database.sessions() as session:
        yield session


DB = Annotated[Session, Depends(get_db)]


def get_user(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    error = HTTPException(
        401,
        "A valid bearer session is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise error
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == token_hash(credentials.credentials))
    ).first()
    if row is None:
        raise error
    session, user = row
    if session.expires_at <= request.app.state.now():
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_user)]


def get_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "admin_only")
    return user


AdminUser = Annotated[User, Depends(get_admin)]
