"""Accounts (#14): validation, argon2, lockout, expiry, isolation and the 18+ gate."""

import logging
from datetime import timedelta

import pytest
from conftest import register
from fastapi.testclient import TestClient

from assistant.backend.config import Settings
from assistant.backend.main import create_app
from assistant.backend.models import User

PASSWORD = "correct-horse-123"


@pytest.fixture
def app(clock, database_url):
    # Production defaults (60-minute sessions), unlike the scheduling fixture.
    return create_app(Settings(database_url=database_url), now=lambda: clock[0])


@pytest.fixture
def client(app):
    with TestClient(app) as instance:
        yield instance


def body(**changes):
    return {
        "name": "Minh",
        "email": "minh@example.com",
        "password": PASSWORD,
        "birth_year": 2004,
        **changes,
    }


def login(client, password=PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"email": "minh@example.com", "password": password}
    )


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_register_stores_argon2_hash_and_age_gate_fields(client, app):
    response = client.post("/api/v1/auth/register", json=body(account_level="k12"))
    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert (user["birth_year"], user["account_level"]) == (2004, "k12")
    assert (user["role"], user["companion_mode"]) == ("student", "buddy")
    with app.state.database.sessions() as db:
        row = db.get(User, user["id"])
        assert row.password_hash.startswith("$argon2id$")
        assert PASSWORD not in row.password_hash
        assert row.adult_verified == 0


def test_duplicate_email_is_409(client):
    assert client.post("/api/v1/auth/register", json=body()).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json=body(email="MINH@example.com"))
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short1"},
        {"password": "only-letters-here"},
        {"password": "1234567890"},
        {"birth_year": 1899},
        {"birth_year": 2999},
        {"account_level": "teacher"},
        {"email": "not-an-email"},
    ],
)
def test_weak_or_invalid_registration_is_422(client, changes):
    assert client.post("/api/v1/auth/register", json=body(**changes)).status_code == 422


def test_wrong_password_and_unknown_email_are_401(client):
    register(client)
    assert login(client, "wrong-password-1").status_code == 401
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert unknown.status_code == 401


def test_five_failures_lock_the_account_for_15_minutes(client, clock):
    register(client)
    for _ in range(4):
        assert login(client, "wrong-password-1").status_code == 401
    assert login(client).status_code == 200  # success resets the counter
    for _ in range(5):
        assert login(client, "wrong-password-1").status_code == 401
    locked = login(client)  # even the right password is refused while locked
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) == 15 * 60
    clock[0] += timedelta(minutes=15, seconds=1)
    assert login(client).status_code == 200


def test_session_expires_after_60_minutes(client, clock):
    token = register(client)["access_token"]
    clock[0] += timedelta(minutes=59)
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 200
    clock[0] += timedelta(minutes=1)
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_missing_or_garbage_token_is_401(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers=auth("forged")).status_code == 401


def test_user_cannot_read_another_users_course(client):
    owner = register(client)["access_token"]
    other = register(client, "Thang", "thang@example.com")["access_token"]
    course = client.post(
        "/api/v1/courses", headers=auth(owner), json={"title": "CSC10014"}
    ).json()
    response = client.get(f"/api/v1/courses/{course['id']}/sources", headers=auth(other))
    assert response.status_code == 404


def test_logs_never_contain_passwords_or_tokens(client, caplog):
    caplog.set_level(logging.INFO)
    token = register(client)["access_token"]
    login(client, "wrong-password-1")
    issued = login(client).json()["access_token"]
    text = caplog.text
    for secret in (PASSWORD, "wrong-password-1", token, issued):
        assert secret not in text
    assert "result=ok" in text and "result=invalid" in text


def test_girlfriend_mode_needs_a_verified_adult_university_account(client, app, clock):
    account = register(client)
    headers = auth(account["access_token"])
    choose = {"companion_mode": "girlfriend"}
    assert client.patch("/api/v1/me", headers=headers, json=choose).status_code == 403
    with app.state.database.sessions() as db:
        user = db.get(User, account["user"]["id"])
        user.adult_verified = 1
        user.birth_year = clock[0].year - 18  # birthday may not have happened yet
        db.commit()
    assert client.patch("/api/v1/me", headers=headers, json=choose).status_code == 403
    with app.state.database.sessions() as db:
        db.get(User, account["user"]["id"]).birth_year = clock[0].year - 19
        db.commit()
    accepted = client.patch("/api/v1/me", headers=headers, json=choose)
    assert accepted.json()["companion_mode"] == "girlfriend"
    with app.state.database.sessions() as db:
        db.get(User, account["user"]["id"]).account_level = "k12"
        db.commit()
    # A stored mode is re-checked at chat time, so the persona falls back to buddy.
    reply = client.post("/api/v1/ai/chat", headers=headers, json={"message": "hi"})
    assert reply.status_code == 200


def test_companion_off_and_chat_rate_limit(client, clock):
    headers = auth(register(client)["access_token"])
    for _ in range(10):
        ok = client.post("/api/v1/ai/chat", headers=headers, json={"message": "hi"})
        assert ok.status_code == 200
    limited = client.post("/api/v1/ai/chat", headers=headers, json={"message": "hi"})
    assert limited.status_code == 429
    clock[0] += timedelta(minutes=1)
    assert (
        client.post("/api/v1/ai/chat", headers=headers, json={"message": "hi"}).status_code
        == 200
    )
    client.patch("/api/v1/me", headers=headers, json={"companion_mode": "off"})
    off = client.post("/api/v1/ai/chat", headers=headers, json={"message": "hi"})
    assert off.status_code == 403
