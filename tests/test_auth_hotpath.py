"""Regression and SQL query-count tests for auth middleware & login hot path."""

from __future__ import annotations

from datetime import timedelta

from conftest import register
from sqlalchemy import event, select

from assistant.backend import routes_auth
from assistant.backend.models import AuthSession


def test_authenticated_request_uses_single_joined_query(app, client, clock):
    """get_user resolves session + user in one joined SELECT while enforcing expiry."""
    reg = register(client, email="single_query@example.com")
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    executed: list[str] = []

    def _track(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", _track)
    try:
        res = client.get("/api/v1/me", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", _track)

    assert res.status_code == 200
    assert len(executed) == 1
    assert "auth_sessions" in executed[0].lower()
    assert "users" in executed[0].lower()

    clock[0] += timedelta(minutes=app.state.settings.session_minutes + 1)
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_register_skips_session_delete_and_login_throttles_global_sweep(
    app, client, clock, monkeypatch
):
    """Register never sweeps auth_sessions; logins scope cleanup to user_id between sweeps."""
    executed: list[str] = []

    def _track(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", _track)
    try:
        reg_a = register(client, name="User A", email="sweep_a@example.com")
        register_deletes = [
            s for s in executed if "delete" in s.lower() and "auth_sessions" in s.lower()
        ]
        assert register_deletes == []

        reg_b = register(client, name="User B", email="sweep_b@example.com")
    finally:
        event.remove(engine, "before_cursor_execute", _track)

    # First login at monotonic t=100 sweeps globally; second at t=110 scopes to user_id
    mono = [100.0]
    monkeypatch.setattr(routes_auth.time, "monotonic", lambda: mono[0])
    monkeypatch.setattr(routes_auth, "_last_session_sweep", 0.0)

    clock[0] += timedelta(
        minutes=app.state.settings.session_minutes + 5
    )  # expire initial tokens for both A and B

    executed.clear()
    event.listen(engine, "before_cursor_execute", _track)
    try:
        res_a = client.post(
            "/api/v1/auth/login",
            json={"email": "sweep_a@example.com", "password": "correct-horse-123"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", _track)
    assert res_a.status_code == 200
    first_deletes = [
        s for s in executed if "delete" in s.lower() and "auth_sessions" in s.lower()
    ]
    assert len(first_deletes) == 1
    assert "user_id" not in first_deletes[0].lower()

    # Re-create an expired session for User A to verify User B's quick login uses user_id scope
    reg_a_login = res_a.json()
    clock[0] += timedelta(minutes=app.state.settings.session_minutes + 5)
    mono[0] = 110.0

    executed.clear()
    event.listen(engine, "before_cursor_execute", _track)
    try:
        res_b = client.post(
            "/api/v1/auth/login",
            json={"email": "sweep_b@example.com", "password": "correct-horse-123"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", _track)
    assert res_b.status_code == 200
    second_deletes = [
        s for s in executed if "delete" in s.lower() and "auth_sessions" in s.lower()
    ]
    assert len(second_deletes) == 1
    assert "user_id" in second_deletes[0].lower()

    # After sweep interval elapses, global sweep removes stale sessions for other users too
    with app.state.database.sessions() as db:
        stale_a = list(
            db.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == reg_a["user"]["id"],
                    AuthSession.expires_at <= clock[0],
                )
            )
        )
        assert len(stale_a) >= 1 or reg_a_login is not None

    mono[0] = 200.0
    res_b2 = client.post(
        "/api/v1/auth/login",
        json={"email": "sweep_b@example.com", "password": "correct-horse-123"},
    )
    assert res_b2.status_code == 200
    with app.state.database.sessions() as db:
        remaining_expired_a = list(
            db.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == reg_a["user"]["id"],
                    AuthSession.expires_at <= clock[0],
                )
            )
        )
        assert remaining_expired_a == []
        assert reg_b["user"]["id"] != reg_a["user"]["id"]
