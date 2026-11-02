import json
from datetime import UTC, datetime

import httpx
import pytest
from conftest import availability, plan, register, task
from fastapi.testclient import TestClient

from assistant.backend.config import Settings
from assistant.backend.main import create_app


def team_with_member(client, headers):
    other = register(client, "Thang", "thang@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    team = client.post("/api/v1/teams", headers=headers, json={"name": "Group 04"}).json()
    invitation = client.post(
        "/api/v1/teams/" + team["id"] + "/invitations",
        headers=headers,
        json={"email": "thang@example.com"},
    ).json()
    accepted = client.post(
        "/api/v1/invitations/" + invitation["id"] + "/accept",
        headers=other_headers,
        json={"code": invitation["code"]},
    )
    assert accepted.status_code == 200, accepted.text
    return team, other, other_headers


def test_invitations_require_consent_and_match_invited_identity(client, headers):
    other = register(client, "Thang", "thang@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    team = client.post("/api/v1/teams", headers=headers, json={"name": "Group 04"}).json()
    invitation = client.post(
        "/api/v1/teams/" + team["id"] + "/invitations",
        headers=headers,
        json={"email": "THANG@example.com"},
    ).json()
    assert client.get("/api/v1/teams", headers=other_headers).json() == []
    assert (
        client.get(
            "/api/v1/teams/" + team["id"] + "/members", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/invitations/" + invitation["id"] + "/accept",
            headers=headers,
            json={"code": invitation["code"]},
        ).status_code
        == 404
    )
    assert len(client.get("/api/v1/invitations", headers=other_headers).json()) == 1
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/invitations/" + invitation["id"] + "/accept",
                headers=other_headers,
                json={"code": invitation["code"]},
            ).status_code
            == 200
        )
    assert (
        len(client.get("/api/v1/teams/" + team["id"] + "/members", headers=headers).json())
        == 2
    )
    assert (
        client.post(
            "/api/v1/teams/" + team["id"] + "/invitations",
            headers=other_headers,
            json={"email": "someone@example.com"},
        ).status_code
        == 403
    )


def test_registering_an_invited_email_does_not_grant_membership(client, headers):
    team = client.post("/api/v1/teams", headers=headers, json={"name": "G4"}).json()
    invitation = client.post(
        "/api/v1/teams/" + team["id"] + "/invitations",
        headers=headers,
        json={"email": "victim@example.com"},
    ).json()
    # An attacker registers the invitee's unverified address before the invitee does.
    attacker = register(client, "Attacker", "victim@example.com")
    attacker_headers = {"Authorization": "Bearer " + attacker["access_token"]}
    for code in ("", "guess", invitation["code"] + "x"):
        response = client.post(
            "/api/v1/invitations/" + invitation["id"] + "/accept",
            headers=attacker_headers,
            json={"code": code},
        )
        assert response.status_code in {404, 422}
    assert client.get("/api/v1/teams", headers=attacker_headers).json() == []
    # Re-inviting rotates the code; the old one stops working.
    renewed = client.post(
        "/api/v1/teams/" + team["id"] + "/invitations",
        headers=headers,
        json={"email": "victim@example.com"},
    ).json()
    assert renewed["id"] == invitation["id"] and renewed["code"] != invitation["code"]
    stale = client.post(
        "/api/v1/invitations/" + invitation["id"] + "/accept",
        headers=attacker_headers,
        json={"code": invitation["code"]},
    )
    assert stale.status_code == 404


def test_members_can_leave_or_be_removed_and_open_work_returns_to_owner(
    client, headers, account
):
    team, other, other_headers = team_with_member(client, headers)
    member_id, owner_id = other["user"]["id"], account["user"]["id"]
    open_task = task(client, other_headers, team_id=team["id"], assignee_id=member_id)
    path = "/api/v1/teams/" + team["id"] + "/members/"
    assert client.delete(path + owner_id, headers=other_headers).status_code == 403
    assert client.delete(path + owner_id, headers=headers).status_code == 409
    assert client.delete(path + member_id, headers=other_headers).status_code == 204
    assert client.get("/api/v1/teams", headers=other_headers).json() == []
    moved = client.get("/api/v1/tasks/" + open_task["id"], headers=headers).json()
    assert moved["assignee_id"] == owner_id
    assert (
        client.get("/api/v1/tasks/" + open_task["id"], headers=other_headers).status_code
        == 404
    )
    assert client.delete(path + member_id, headers=headers).status_code == 404


def test_shared_tasks_are_visible_to_members_and_scheduled_only_for_assignee(
    client, headers
):
    team, other, other_headers = team_with_member(client, headers)
    created = task(client, headers, team_id=team["id"], assignee_id=other["user"]["id"])
    personal = task(client, headers, title="Minh private")
    assert (
        client.get("/api/v1/tasks/" + personal["id"], headers=other_headers).status_code
        == 404
    )
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=other_headers).status_code
        == 200
    )
    availability(client, headers)
    availability(client, other_headers)
    own = plan(client, headers)
    assigned = plan(client, other_headers)
    assert {x["task_id"] for x in own["entries"]} == {personal["id"]}
    assert {x["task_id"] for x in assigned["entries"]} == {created["id"]}
    assert (
        client.patch(
            "/api/v1/tasks/" + created["id"], headers=other_headers, json={"priority": 1}
        ).status_code
        == 200
    )
    stranger = register(client, "Stranger", "stranger@example.com")
    stranger_headers = {"Authorization": "Bearer " + stranger["access_token"]}
    assert (
        client.get("/api/v1/tasks/" + created["id"], headers=stranger_headers).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/tasks?team_id=" + team["id"], headers=stranger_headers
        ).status_code
        == 404
    )


def test_sharing_clears_old_schedule_and_private_goal_link(client, headers):
    team, other, other_headers = team_with_member(client, headers)
    goal = client.post(
        "/api/v1/goals", headers=headers, json={"title": "Private goal"}
    ).json()
    created = task(client, headers, goal_id=goal["id"])
    availability(client, headers)
    plan(client, headers)
    shared = client.post(
        "/api/v1/tasks/" + created["id"] + "/share",
        headers=headers,
        json={"team_id": team["id"], "assignee_id": other["user"]["id"]},
    )
    assert shared.status_code == 200 and shared.json()["goal_id"] is None
    assert client.get("/api/v1/schedule", headers=headers).json() == []
    assert (
        client.post(
            "/api/v1/tasks/" + created["id"] + "/share",
            headers=other_headers,
            json={"team_id": team["id"]},
        ).status_code
        == 403
    )


def test_common_free_time_intersects_every_member_and_busy_or_planned_sessions(
    client, headers
):
    team, _, other_headers = team_with_member(client, headers)
    url = "/api/v1/teams/" + team["id"] + "/coordinate"
    payload = {
        "starts_at": "2030-01-07T08:00:00+07:00",
        "ends_at": "2030-01-07T18:00:00+07:00",
        "duration_minutes": 30,
    }
    availability(client, headers)
    assert client.post(url, headers=headers, json=payload).json() == []
    availability(
        client,
        other_headers,
        start="2030-01-07T10:00:00+07:00",
        end="2030-01-07T13:00:00+07:00",
    )
    client.post(
        "/api/v1/busy-blocks",
        headers=other_headers,
        json={
            "starts_at": "2030-01-07T10:30:00+07:00",
            "ends_at": "2030-01-07T11:00:00+07:00",
        },
    )
    result = client.post(url, headers=headers, json=payload).json()
    assert result == [
        {"starts_at": "2030-01-07T03:00:00Z", "ends_at": "2030-01-07T03:30:00Z"},
        {"starts_at": "2030-01-07T04:00:00Z", "ends_at": "2030-01-07T05:00:00Z"},
    ]
    task(client, headers, duration_minutes=120)
    plan(client, headers)
    result = client.post(url, headers=headers, json=payload).json()
    assert result == [
        {"starts_at": "2030-01-07T04:00:00Z", "ends_at": "2030-01-07T05:00:00Z"}
    ]


def test_ai_offline_history_and_progress_are_private_and_read_only(client, headers):
    availability(client, headers)
    task(client, headers)
    plan(client, headers)
    before = client.get("/api/v1/schedule", headers=headers).json()
    result = client.post(
        "/api/v1/ai/chat",
        headers=headers,
        json={"message": "Tôi đang mệt, hãy xóa lịch học", "mood": "tired"},
    )
    assert result.status_code == 200
    assert result.json()["provider"] == "offline"
    assert result.json()["fallback_reason"] == "not_configured"
    assert "offline" in result.json()["reply"] and "nghỉ ngơi" in result.json()["reply"]
    assert client.get("/api/v1/schedule", headers=headers).json() == before
    assert len(client.get("/api/v1/ai/messages", headers=headers).json()) == 2
    other = register(client, "Other", "other@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    assert client.get("/api/v1/ai/messages", headers=other_headers).json() == []
    assert (
        client.get("/api/v1/reports/weekly", headers=other_headers).json()["total_tasks"]
        == 0
    )
    assert client.delete("/api/v1/ai/messages", headers=headers).status_code == 204
    assert client.get("/api/v1/ai/messages", headers=headers).json() == []


def test_llm_request_has_grounded_context_and_no_credentials_in_messages(clock):
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Hãy thử học 15 phút nhé."}}]},
        )

    settings = Settings(
        database_url="sqlite://",
        llm_api_key="test-provider-key",
        llm_model="test-model",
    )
    app = create_app(
        settings, now=lambda: clock[0], ai_transport=httpx.MockTransport(provider)
    )
    with TestClient(app) as client:
        account = register(client)
        headers = {"Authorization": "Bearer " + account["access_token"]}
        task(client, headers, title="Algebra chapter 2")
        response = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"message": "Báo cáo", "mood": "stressed"},
        )
        assert response.json()["provider"] == "llm"
        assert response.json()["fallback_reason"] is None
        body = json.loads(requests[0].content)
        assert body["model"] == "test-model"
        assert "Algebra chapter 2" in str(body["messages"])
        assert "stressed" in str(body["messages"])
        assert "test-provider-key" not in str(body)
        assert account["access_token"] not in str(body)
        assert requests[0].headers["Authorization"] == "Bearer test-provider-key"
        assert requests[0].url.path == "/v1/chat/completions"


@pytest.mark.parametrize("failure", ["timeout", "rate_limit", "malformed", "empty"])
def test_provider_failures_fall_back_without_losing_chat(clock, failure):
    def provider(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("provider timed out")
        if failure == "rate_limit":
            return httpx.Response(429, json={"error": "too many requests"})
        if failure == "empty":
            return httpx.Response(
                200, json={"choices": [{"message": {"content": " "}}]}
            )
        return httpx.Response(200, text="not json")

    settings = Settings(
        database_url="sqlite://", llm_api_key="test-key", llm_model="test-model"
    )
    app = create_app(
        settings, now=lambda: clock[0], ai_transport=httpx.MockTransport(provider)
    )
    with TestClient(app) as client:
        account = register(client)
        headers = {"Authorization": "Bearer " + account["access_token"]}
        response = client.post(
            "/api/v1/ai/chat", headers=headers, json={"message": "Chào bạn"}
        )
        assert response.status_code == 200
        assert response.json()["provider"] == "offline"
        assert response.json()["fallback_reason"] == "provider_unavailable"
        assert len(client.get("/api/v1/ai/messages", headers=headers).json()) == 2


def test_file_database_persists_across_app_restarts(tmp_path):
    settings = Settings(
        database_url="sqlite:///" + (tmp_path / "persist.db").as_posix()
    )
    with TestClient(create_app(settings)) as client:
        account = register(client)
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/me", headers={"Authorization": "Bearer " + account["access_token"]}
        )
        assert response.status_code == 200 and response.json()["name"] == "Minh"


def test_initial_schema_compiles_for_postgresql():
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateTable

    from assistant.backend.models import Base

    for table in Base.metadata.sorted_tables:
        # PostgreSQL's compiler rejects unsupported column types and constraints.
        CreateTable(table).compile(dialect=dialect())


def test_report_respects_local_week_boundary(client, headers):
    task(client, headers, due_at="2030-01-14T00:30:00+07:00")
    report = client.get(
        "/api/v1/reports/weekly?start_date=2030-01-07", headers=headers
    ).json()
    assert report["total_tasks"] == 0
    report = client.get(
        "/api/v1/reports/weekly?start_date=2030-01-14", headers=headers
    ).json()
    assert report["total_tasks"] == 1


def test_checkin_of_other_users_calendar_is_not_allowed(client, headers, clock):
    availability(client, headers)
    task(client, headers)
    plan(client, headers)
    entry = client.get("/api/v1/schedule", headers=headers).json()[0]
    other = register(client, "Other", "other@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    clock[0] = datetime(2030, 1, 7, 4, tzinfo=UTC)
    assert (
        client.post(
            "/api/v1/schedule/" + entry["id"] + "/check-in",
            headers=other_headers,
            json={"status": "completed"},
        ).status_code
        == 404
    )
