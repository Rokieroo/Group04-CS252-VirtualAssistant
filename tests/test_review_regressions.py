from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import pytest
from conftest import availability, plan, register, task
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from assistant.backend import services
from assistant.backend.config import Settings
from assistant.backend.main import create_app
from assistant.backend.models import Task, User
from assistant.backend.routes_schedule import check_in
from assistant.backend.routes_tasks import update_task
from assistant.backend.schemas import CheckIn, TaskPatch


def test_task_update_rechecks_progress_after_acquiring_assignee_lock(
    client, app, headers, account, clock
):
    availability(client, headers)
    created = task(client, headers, duration_minutes=60)
    plan(client, headers)
    entry = client.get("/api/v1/schedule", headers=headers).json()[0]
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    request = SimpleNamespace(app=app)
    with (
        app.state.database.sessions() as earlier,
        app.state.database.sessions() as later,
    ):
        stale_task = earlier.get(Task, created["id"])
        assert stale_task.status == "pending"
        owner = earlier.get(User, account["user"]["id"])
        check_in(
            entry["id"],
            CheckIn(status="completed"),
            request,
            later,
            later.get(User, owner.id),
        )
        with pytest.raises(HTTPException) as denied:
            update_task(
                created["id"], TaskPatch(status="cancelled"), request, earlier, owner
            )
        assert denied.value.status_code == 409
    current = client.get("/api/v1/tasks/" + created["id"], headers=headers).json()
    assert current["status"] == "completed" and current["completed_minutes"] == 60


def test_delete_and_checkin_cannot_both_succeed_and_erase_history(tmp_path):
    clock = [datetime(2030, 1, 7, 0, tzinfo=UTC)]
    settings = Settings(
        database_url="sqlite:///" + (tmp_path / "race.db").as_posix(),
        session_minutes=43200,
    )
    app = create_app(settings, now=lambda: clock[0])
    reached_delete, release_delete, checkin_finished = Event(), Event(), Event()

    def pause_delete(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("DELETE FROM schedule_entries")
            and "schedule_entries.status" not in statement
        ):
            reached_delete.set()
            assert release_delete.wait(5), "Timed out releasing the controlled delete"

    with TestClient(app) as client:
        account = register(client)
        headers = {"Authorization": "Bearer " + account["access_token"]}
        availability(client, headers)
        created = task(client, headers, duration_minutes=60)
        plan(client, headers)
        entry = client.get("/api/v1/schedule", headers=headers).json()[0]
        clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
        event.listen(app.state.database.engine, "before_cursor_execute", pause_delete)

        def complete():
            try:
                return client.post(
                    "/api/v1/schedule/" + entry["id"] + "/check-in",
                    headers=headers,
                    json={"status": "completed"},
                )
            finally:
                checkin_finished.set()

        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                deletion = workers.submit(
                    client.delete, "/api/v1/tasks/" + created["id"], headers=headers
                )
                assert reached_delete.wait(5)
                completion = workers.submit(complete)
                # An unprotected check-in finishes here; a protected one waits for deletion.
                checkin_finished.wait(0.3)
                release_delete.set()
                deleted, completed = (
                    deletion.result(timeout=5),
                    completion.result(timeout=5),
                )
        finally:
            release_delete.set()
            event.remove(
                app.state.database.engine, "before_cursor_execute", pause_delete
            )
        assert (deleted.status_code, completed.status_code) in {(204, 404), (409, 200)}
        if completed.status_code == 200:
            saved = client.get("/api/v1/schedule", headers=headers).json()
            assert any(
                row["id"] == entry["id"] and row["actual_minutes"] == 60
                for row in saved
            )


def test_availability_change_cannot_interleave_with_committed_plan(
    tmp_path, monkeypatch
):
    clock = datetime(2030, 1, 7, 0, tzinfo=UTC)
    settings = Settings(
        database_url="sqlite:///" + (tmp_path / "plan-race.db").as_posix(),
        session_minutes=43200,
    )
    app = create_app(settings, now=lambda: clock)
    reached_insert, release_insert, availability_finished = Event(), Event(), Event()

    real_builder = services.build_plan

    def pause_plan(*args, **kwargs):
        result = real_builder(*args, **kwargs)
        reached_insert.set()
        assert release_insert.wait(5), "Timed out releasing the controlled plan"
        return result

    monkeypatch.setattr(services, "build_plan", pause_plan)

    with TestClient(app) as client:
        account = register(client)
        headers = {"Authorization": "Bearer " + account["access_token"]}
        availability(client, headers)
        task(client, headers, duration_minutes=60)

        def clear_windows():
            try:
                return client.put(
                    "/api/v1/availability", headers=headers, json={"windows": []}
                )
            finally:
                availability_finished.set()

        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                planning = workers.submit(plan, client, headers)
                assert reached_insert.wait(5)
                clearing = workers.submit(clear_windows)
                availability_finished.wait(0.3)
                release_insert.set()
                planning.result(timeout=5)
                assert clearing.result(timeout=5).status_code == 200
        finally:
            release_insert.set()
        assert client.get("/api/v1/availability", headers=headers).json() == []
        assert client.get("/api/v1/schedule", headers=headers).json() == []


def test_replan_recovers_past_unchecked_work_without_changing_history_during_preview(
    client, headers, clock
):
    availability(client, headers)
    created = task(client, headers, duration_minutes=60)
    plan(client, headers)
    old_entry = client.get("/api/v1/schedule", headers=headers).json()[0]
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    request = {
        "starts_at": "2030-01-07T10:00:00+07:00",
        "ends_at": "2030-01-07T12:00:00+07:00",
    }
    preview = client.post("/api/v1/schedule/replan", headers=headers, json=request)
    assert preview.status_code == 200
    assert preview.json()["entries"] == [
        {
            "task_id": created["id"],
            "starts_at": "2030-01-07T03:00:00Z",
            "ends_at": "2030-01-07T04:00:00Z",
        }
    ]
    assert preview.json()["expired_sessions"] == 1
    assert client.get("/api/v1/schedule", headers=headers).json()[0]["status"] == "planned"
    committed = client.post(
        "/api/v1/schedule/replan", headers=headers, json={**request, "commit": True}
    )
    assert committed.status_code == 200
    entries = client.get("/api/v1/schedule", headers=headers).json()
    assert (
        next(row for row in entries if row["id"] == old_entry["id"])["status"]
        == "missed"
    )
    assert len([row for row in entries if row["status"] == "planned"]) == 1
    current = client.get("/api/v1/tasks/" + created["id"], headers=headers).json()
    assert current["completed_minutes"] == 0
