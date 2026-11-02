"""JWT integration boundary for #14; never trusts client-supplied owner IDs."""
import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

bearer = HTTPBearer(auto_error=False)


def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})


def session(request: Request):
    with get_session(request.app.state.database_url) as database:
        yield database


Database = Annotated[Session, Depends(session)]


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 database: Database) -> str:
    if credentials is None:
        fail(401, "unauthorized", "A bearer token is required.")
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret.encode()) < 32:
        fail(503, "auth_not_configured", "Configure JWT_SECRET with at least 32 bytes.")
    try:
        claims = jwt.decode(credentials.credentials, secret, algorithms=["HS256"],
                            options={"require": ["sub", "exp"]})
        user_id = claims["sub"]
        if not isinstance(user_id, str) or not user_id:
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        fail(401, "unauthorized", "Invalid or expired token.")
    if not database.execute(text("SELECT id FROM users WHERE id=:id"), {"id": user_id}).first():
        fail(401, "unauthorized", "Account not found.")
    return user_id


User = Annotated[str, Depends(current_user)]


def owned_course(database, course_id: str, user_id: str):
    row = database.execute(text("SELECT * FROM courses WHERE id=:id AND owner_id=:owner"),
                           {"id": course_id, "owner": user_id}).mappings().first()
    if row is None:
        fail(404, "not_found", "Course not found.")
    return row
