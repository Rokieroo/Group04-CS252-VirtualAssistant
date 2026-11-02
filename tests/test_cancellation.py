from datetime import UTC, datetime

from conftest import availability, plan, task
from test_teams_ai import team_with_member


def test_cancelling_an_underway_task_clears_unchecked_sessions(client, headers, clock):
    availability(client, headers)
    created = task(client, headers)
    plan(client, headers)
    clock[0] = datetime(2030, 1, 7, 2, 30, tzinfo=UTC)
    response = client.patch(
        "/api/v1/tasks/" + created["id"], headers=headers, json={"status": "cancelled"}
    )
    assert response.status_code == 200
    assert client.get("/api/v1/schedule", headers=headers).json() == []


def test_reassigning_after_session_start_removes_old_unchecked_sessions(
    client, headers, clock
):
    team, other, _ = team_with_member(client, headers)
    availability(client, headers)
    created = task(client, headers)
    plan(client, headers)
    old_entry = client.get("/api/v1/schedule", headers=headers).json()[0]
    clock[0] = datetime(2030, 1, 7, 3, tzinfo=UTC)
    response = client.post(
        "/api/v1/tasks/" + created["id"] + "/share",
        headers=headers,
        json={"team_id": team["id"], "assignee_id": other["user"]["id"]},
    )
    assert response.status_code == 200
    assert client.get("/api/v1/schedule", headers=headers).json() == []
    assert (
        client.post(
            "/api/v1/schedule/" + old_entry["id"] + "/check-in",
            headers=headers,
            json={"status": "completed"},
        ).status_code
        == 404
    )
