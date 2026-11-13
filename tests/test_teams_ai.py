"""Companion AI, weekly reports, and database persistence tests (issue #167)."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from conftest import availability, plan, register, task
from fastapi.testclient import TestClient

from assistant.backend.config import Settings
from assistant.backend.main import create_app


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
