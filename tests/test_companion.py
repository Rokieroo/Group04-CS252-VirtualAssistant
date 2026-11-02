"""Companion logic without HTTP routes or a database (ADR 003)."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.companion import (
    ChatProvider,
    Companion,
    CompanionContext,
    NextSession,
    ProviderUnavailable,
)

REPORT = {"completed_minutes": 45, "completed_tasks": 1, "total_tasks": 3}


def context(**changes):
    values = {
        "name": "An",
        "timezone": "Asia/Ho_Chi_Minh",
        "mood": "neutral",
        "mode": "buddy",
        "personality": "warm",
        "weekly_progress": REPORT,
        "next_session": NextSession("Algebra", datetime(2030, 1, 7, 2, tzinfo=UTC)),
        "history": [("user", "Chào"), ("assistant", "Chào An")],
    }
    return CompanionContext(**(values | changes))


class StubProvider:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.messages = reply, error, None

    def complete(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.reply


def test_without_provider_the_reply_is_offline_and_grounded():
    reply = Companion().reply(context(mood="tired"), "Hi")
    assert (reply.provider, reply.fallback_reason) == ("offline", "not_configured")
    assert "45 phút" in reply.text and "1/3" in reply.text
    assert "Algebra, lúc 09:00 07/01" in reply.text  # local time, not UTC
    assert "nghỉ ngơi" in reply.text


def test_provider_gets_prompt_facts_history_then_message_in_order():
    provider = StubProvider("Học 15 phút nhé.")
    reply = Companion(provider).reply(context(), "Báo cáo")
    assert (reply.text, reply.provider, reply.fallback_reason) == (
        "Học 15 phút nhé.",
        "llm",
        None,
    )
    roles = [message["role"] for message in provider.messages]
    assert roles == ["system", "user", "user", "assistant", "user"]
    facts = json.loads(provider.messages[1]["content"].split("\n", 1)[1])
    assert facts["next_session"]["title"] == "Algebra"
    assert provider.messages[-1]["content"] == "Báo cáo"


def test_provider_failure_falls_back_offline():
    provider = StubProvider(error=ProviderUnavailable("ReadTimeout"))
    reply = Companion(provider).reply(context(next_session=None), "Hi")
    assert (reply.provider, reply.fallback_reason) == ("offline", "provider_unavailable")
    assert "thêm giờ rảnh" in reply.text


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
    ],
)
def test_chat_provider_turns_every_bad_response_into_provider_unavailable(response):
    provider = ChatProvider(
        "https://llm.test/v1/", "key", "model", 5, httpx.MockTransport(lambda _: response)
    )
    with pytest.raises(ProviderUnavailable):
        provider.complete([{"role": "user", "content": "Hi"}])
