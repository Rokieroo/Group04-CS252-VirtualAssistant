"""Request-scoped database session and authenticated identity."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
    session = db.get(AuthSession, token_hash(credentials.credentials))
    if session is None or session.expires_at <= request.app.state.now():
        raise error
    user = db.get(User, session.user_id)
    if user is None:
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_user)]


def get_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "admin_only")
    return user


AdminUser = Annotated[User, Depends(get_admin)]
