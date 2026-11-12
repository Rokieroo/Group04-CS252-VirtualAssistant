from datetime import UTC, datetime

from conftest import availability, plan, task


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
