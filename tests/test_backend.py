from datetime import UTC, datetime, timedelta

import pytest
from conftest import availability, plan, register, task
from sqlalchemy import event, select

from assistant.backend.models import AuthSession, User


def test_accounts_hash_password_and_sessions_and_revoke(
    client, app, account, headers, clock
):
    assert "password" not in str(account)
    with app.state.database.sessions() as db:
        user = db.get(User, account["user"]["id"])
        assert user.password_hash.startswith("$argon2id$")
        assert "correct-horse-123" not in user.password_hash
        session = db.scalar(select(AuthSession))
        assert session.token_hash != account["access_token"]
    assert client.get("/api/v1/me", headers=headers).json()["name"] == "Minh"
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "MINH@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    logged = client.post(
        "/api/v1/auth/login",
        json={"email": "MINH@example.com", "password": "correct-horse-123"},
    )
    assert logged.status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    new_headers = {"Authorization": "Bearer " + logged.json()["access_token"]}
    clock[0] += timedelta(days=31)  # past the fixture's 30-day session
    assert client.get("/api/v1/me", headers=new_headers).status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/me",
        "/api/v1/tasks",
        "/api/v1/goals",
        "/api/v1/schedule",
        "/api/v1/ai/messages",
        "/api/v1/teams",
        "/api/v1/notifications",
        "/api/v1/reports/weekly",
    ],
)
def test_private_endpoints_require_authentication(client, path):
    assert client.get(path).status_code == 401


def test_register_duplicates_input_and_profile_validation(client, headers):
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "name": "Other",
                "email": "MINH@example.com",
                "password": "long-enough-123",
                "birth_year": 2004,
            },
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/api/v1/me", headers=headers, json={"timezone": "Imaginary/Place"}
        ).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/me", headers=headers, json={"name": None}).status_code == 422
    )
    assert (
        client.patch(
            "/api/v1/me", headers=headers, json={"personality": "possessive"}
        ).status_code
        == 422
    )
    result = client.patch(
        "/api/v1/me",
        headers=headers,
        json={"personality": "direct", "timezone": "Asia/Saigon"},
    )
    assert result.status_code == 200
    assert result.json()["timezone"] == "Asia/Saigon"


def test_goal_crud_and_foreign_goal_protection(client, headers):
    goal = client.post(
        "/api/v1/goals", headers=headers, json={"title": "Pass CS252"}
    ).json()
    created = task(client, headers, goal_id=goal["id"])
    other = register(client, "Thang", "thang@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    for method in ("get", "patch", "delete"):
        kwargs = {"json": {"title": "stolen"}} if method == "patch" else {}
        assert (
            getattr(client, method)(
                "/api/v1/goals/" + goal["id"], headers=other_headers, **kwargs
            ).status_code
            == 404
        )
    denied = client.post(
        "/api/v1/tasks",
        headers=other_headers,
        json={
            "title": "No",
            "duration_minutes": 30,
            "due_at": "2030-01-08T00:00:00Z",
            "goal_id": goal["id"],
        },
    )
    assert denied.status_code == 404
    assert (
        client.patch(
            "/api/v1/goals/" + goal["id"], headers=headers, json={"title": "Finish CS252"}
        ).status_code
        == 200
    )
    assert client.delete("/api/v1/goals/" + goal["id"], headers=headers).status_code == 204
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=headers).json()["goal_id"]
        is None
    )


def test_task_crud_validation_and_isolation(client, headers):
    created = task(client, headers)
    other = register(client, "Other", "other@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    assert client.get("/api/v1/tasks", headers=other_headers).json() == []
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=other_headers).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=other_headers, json={"title": "No"}
        ).status_code
        == 404
    )
    assert (
        client.delete("/api/v1/tasks/" + created["id"], headers=other_headers).status_code
        == 404
    )
    for changes in (
        {"duration_minutes": 0},
        {"priority": 4},
        {"title": "  "},
        {"due_at": "2029-01-01T00:00:00Z"},
        {"due_at": "2030-01-08T09:00:00"},
    ):
        payload = {
            "title": "Bad",
            "duration_minutes": 30,
            "due_at": "2030-01-08T09:00:00Z",
            **changes,
        }
        assert (
            client.post("/api/v1/tasks", headers=headers, json=payload).status_code == 422
        )
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=headers, json={"title": None}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=headers, json={"title": "Geometry"}
        ).status_code
        == 200
    )
    assert (
        client.delete("/api/v1/tasks/" + created["id"], headers=headers).status_code == 204
    )
    assert client.get("/api/v1/tasks", headers=headers).json() == []


def test_task_date_filter_uses_users_local_day(client, headers):
    created = task(client, headers, due_at="2030-01-08T00:30:00+07:00")
    assert client.get("/api/v1/tasks?date=2030-01-07", headers=headers).json() == []
    assert (
        client.get("/api/v1/tasks?date=2030-01-08", headers=headers).json()[0]["id"]
        == created["id"]
    )


def test_preview_commit_repeat_replan_and_capacity(client, headers):
    availability(client, headers)
    created = task(client, headers)
    preview = plan(client, headers, commit=False)
    assert preview["committed"] is False and len(preview["entries"]) == 2
    assert client.get("/api/v1/schedule", headers=headers).json() == []
    first = plan(client, headers)
    assert first["committed"] is True
    second = plan(client, headers)
    assert first["entries"] == second["entries"]
    assert len(client.get("/api/v1/schedule", headers=headers).json()) == 2
    no_capacity = plan(client, headers, daily_limit_minutes=30)
    assert no_capacity["unscheduled"] == [
        {"task_id": created["id"], "minutes": 60, "reason": "insufficient_capacity"}
    ]


def test_plan_without_availability_reports_unscheduled(client, headers):
    created = task(client, headers)
    result = plan(client, headers)
    assert result["entries"] == []
    assert result["unscheduled"][0]["task_id"] == created["id"]


def test_busy_block_clears_conflicts_and_replan_avoids_them(client, headers):
    availability(client, headers)
    task(client, headers, duration_minutes=150)
    plan(client, headers)
    response = client.post(
        "/api/v1/busy-blocks",
        headers=headers,
        json={
            "starts_at": "2030-01-07T10:00:00+07:00",
            "ends_at": "2030-01-07T11:00:00+07:00",
            "title": "Class",
        },
    )
    assert response.status_code == 201
    result = plan(client, headers)
    assert result["unscheduled"][0]["minutes"] == 30
    assert all(
        x["ends_at"] <= "2030-01-07T03:00:00Z"
        or x["starts_at"] >= "2030-01-07T04:00:00Z"
        for x in result["entries"]
    )
    assert (
        client.delete(
            "/api/v1/busy-blocks/" + response.json()["id"], headers=headers
        ).status_code
        == 204
    )


def test_check_in_idempotency_partial_credit_and_preserved_history(
    client, headers, clock
):
    availability(client, headers)
    created = task(client, headers)
    plan(client, headers)
    first = client.get("/api/v1/schedule", headers=headers).json()[0]
    url = "/api/v1/schedule/" + first["id"] + "/check-in"
    assert (
        client.post(url, headers=headers, json={"status": "completed"}).status_code
        == 409
    )
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    assert (
        client.post(
            url, headers=headers, json={"status": "completed", "actual_minutes": 30}
        ).status_code
        == 200
    )
    assert (
        client.post(
            url, headers=headers, json={"status": "completed", "actual_minutes": 30}
        ).status_code
        == 200
    )
    assert (
        client.post(url, headers=headers, json={"status": "missed"}).status_code == 409
    )
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=headers).json()[
            "completed_minutes"
        ]
        == 30
    )
    plan(client, headers, starts_at="2030-01-07T10:00:00+07:00")
    entries = client.get("/api/v1/schedule", headers=headers).json()
    assert next(x for x in entries if x["id"] == first["id"])["actual_minutes"] == 30
    assert (
        sum(
            int(
                (
                    datetime.fromisoformat(x["ends_at"])
                    - datetime.fromisoformat(x["starts_at"])
                ).total_seconds()
                // 60
            )
            for x in entries
            if x["status"] == "planned"
        )
        == 60
    )
    assert (
        client.delete("/api/v1/tasks/" + created["id"], headers=headers).status_code == 409
    )


def test_missed_sessions_do_not_award_progress_and_can_be_replanned(
    client, headers, clock
):
    availability(client, headers)
    created = task(client, headers, duration_minutes=60)
    plan(client, headers)
    first = client.get("/api/v1/schedule", headers=headers).json()[0]
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    assert (
        client.post(
            "/api/v1/schedule/" + first["id"] + "/check-in",
            headers=headers,
            json={"status": "missed"},
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=headers).json()[
            "completed_minutes"
        ]
        == 0
    )
    result = plan(client, headers, starts_at="2030-01-07T10:00:00+07:00")
    assert len(result["entries"]) == 1
    report = client.get(
        "/api/v1/reports/weekly?start_date=2030-01-07", headers=headers
    ).json()
    assert report["missed_sessions"] == 1 and report["completed_minutes"] == 0


def test_complete_task_report_and_reminders(client, headers, clock):
    availability(client, headers)
    created = task(client, headers, duration_minutes=60)
    plan(client, headers)
    clock[0] = datetime(2030, 1, 7, 1, 50, tzinfo=UTC)
    first = client.get("/api/v1/notifications", headers=headers).json()
    second = client.get("/api/v1/notifications", headers=headers).json()
    reminders = [x for x in first if x["entry_id"]]
    assert len(reminders) == 1 and len(first) == len(second)
    assert (
        client.post(
            "/api/v1/notifications/" + reminders[0]["id"] + "/read", headers=headers
        ).json()["read"]
        is True
    )
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    entry = client.get("/api/v1/schedule", headers=headers).json()[0]
    assert (
        client.post(
            "/api/v1/schedule/" + entry["id"] + "/check-in",
            headers=headers,
            json={"status": "completed"},
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=headers).json()["status"]
        == "completed"
    )
    report = client.get(
        "/api/v1/reports/weekly?start_date=2030-01-07", headers=headers
    ).json()
    assert report["completed_minutes"] == 60 and report["completion_percent"] == 100
    assert not any(
        x["entry_id"] for x in client.get("/api/v1/notifications", headers=headers).json()
    )


def test_changing_availability_and_task_cancels_only_future_plans(client, headers):
    availability(client, headers)
    created = task(client, headers)
    plan(client, headers)
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=headers, json={"priority": 1}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/schedule", headers=headers).json() == []
    plan(client, headers)
    availability(client, headers, end="2030-01-07T11:00:00+07:00")
    assert client.get("/api/v1/schedule", headers=headers).json() == []


def test_cached_weekly_report_updates_after_task_changes(client, headers):
    assert client.get("/api/v1/reports/weekly", headers=headers).json()["total_tasks"] == 0
    created = task(client, headers)
    assert client.get("/api/v1/reports/weekly", headers=headers).json()["total_tasks"] == 1
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=headers, json={"status": "cancelled"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/reports/weekly", headers=headers).json()["total_tasks"] == 0


def test_reading_notifications_never_writes(client, app, headers, clock):
    availability(client, headers)
    task(client, headers, duration_minutes=60)
    plan(client, headers)
    writes = []

    def record(connection, cursor, statement, *args):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    clock[0] = datetime(2030, 1, 7, 1, 44, tzinfo=UTC)
    event.listen(app.state.database.engine, "before_cursor_execute", record)
    try:
        early = client.get("/api/v1/notifications", headers=headers).json()
        clock[0] = datetime(2030, 1, 7, 1, 45, tzinfo=UTC)
        due = client.get("/api/v1/notifications", headers=headers).json()
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", record)
    assert writes == []
    # The reminder appears exactly 15 minutes before the 02:00 UTC session.
    assert not any(x["entry_id"] for x in early)
    assert sum(bool(x["entry_id"]) for x in due) == 1
