"""The authenticated-request and login hot paths (#168)."""

from __future__ import annotations

from datetime import timedelta

from conftest import register
from sqlalchemy import event, select

from assistant.backend import maintenance
from assistant.backend.models import AuthSession


def _statements(app, action):
    executed: list[str] = []

    def track(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement.lower())

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", track)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", track)
    return result, executed


def _sessions_of(app, user_id):
    with app.state.database.sessions() as db:
        return set(db.scalars(select(AuthSession.token_hash).where(AuthSession.user_id == user_id)))


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-123"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_an_authenticated_request_reads_session_and_user_in_one_query(app, client, clock):
    headers = {"Authorization": "Bearer " + register(client)["access_token"]}
    response, executed = _statements(app, lambda: client.get("/api/v1/me", headers=headers))
    assert response.status_code == 200
    assert len(executed) == 1
    assert "auth_sessions" in executed[0] and "users" in executed[0]

    clock[0] += timedelta(minutes=app.state.settings.session_minutes + 1)
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_login_clears_only_its_own_expired_sessions(app, client, clock):
    a = register(client, name="A", email="a@example.com")["user"]["id"]
    b = register(client, name="B", email="b@example.com")["user"]["id"]
    expired_b = _sessions_of(app, b)
    clock[0] += timedelta(minutes=app.state.settings.session_minutes + 1)

    _, executed = _statements(app, lambda: _login(client, "a@example.com"))

    deletes = [s for s in executed if s.startswith("delete from auth_sessions")]
    assert len(deletes) == 1 and "user_id" in deletes[0]
    assert len(_sessions_of(app, a)) == 1  # the expired one went, the new one stayed
    assert _sessions_of(app, b) == expired_b  # left for the daily prune job


def test_the_daily_prune_job_sweeps_every_expired_session(app, client, clock):
    register(client, name="A", email="a@example.com")
    b = register(client, name="B", email="b@example.com")["user"]["id"]
    clock[0] += timedelta(minutes=app.state.settings.session_minutes + 1)
    fresh = _login(client, "b@example.com")

    with app.state.database.sessions() as db:
        assert maintenance.prune(db, {}, clock[0])["auth_sessions"] == 1  # A's
        db.commit()
        assert db.scalars(select(AuthSession.user_id)).all() == [b]
    me = client.get("/api/v1/me", headers={"Authorization": "Bearer " + fresh["access_token"]})
    assert me.status_code == 200
