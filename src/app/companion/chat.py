"""Grounded, read-only companion reply with an explicit offline fallback (UC-07/08).

Knows nothing about HTTP routes or the database: callers hand in a CompanionContext
and persist the CompanionReply themselves.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from app.companion.persona import MODES, PERSONALITIES, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 12000


@dataclass(frozen=True)
class PendingTask:
    title: str
    due_at: datetime
    remaining_minutes: int


@dataclass(frozen=True)
class NextSession:
    title: str
    starts_at: datetime


@dataclass(frozen=True)
class CompanionContext:
    """The only facts the companion may use. Every string in it is untrusted data."""

    name: str
    timezone: str
    mood: str
    mode: str
    personality: str
    weekly_progress: dict  # JSON-ready weekly report
    pending_tasks: list[PendingTask] = field(default_factory=list)
    next_session: NextSession | None = None
    history: list[tuple[str, str]] = field(default_factory=list)  # (role, content)

    def facts(self) -> dict:
        return {
            "name": self.name,
            "timezone": self.timezone,
            "mood": self.mood,
            "weekly_progress": self.weekly_progress,
            "pending_tasks": [
                {
                    "title": task.title,
                    "due_at": task.due_at.isoformat(),
                    "remaining_minutes": task.remaining_minutes,
                }
                for task in self.pending_tasks
            ],
            "next_session": {
                "title": self.next_session.title,
                "starts_at": self.next_session.starts_at.isoformat(),
            }
            if self.next_session
            else None,
        }


@dataclass(frozen=True)
class CompanionReply:
    text: str
    provider: Literal["llm", "offline"]
    fallback_reason: str | None = None


class ProviderUnavailable(Exception):
    """The chat provider failed; the message is the underlying error type."""


class ChatProvider:
    """OpenAI-compatible /chat/completions client. Holds no conversation state."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def complete(self, messages: list[dict]) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = client.post(
                    self.url,
                    headers={"Authorization": "Bearer " + self.api_key},
                    json={"model": self.model, "messages": messages},
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise ProviderUnavailable(type(exc).__name__) from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderUnavailable("EmptyResponse")
        return content.strip()


class Companion:
    """Answers through the provider when one is configured, otherwise offline."""

    def __init__(self, provider: ChatProvider | None = None):
        self.provider = provider

    def reply(self, context: CompanionContext, message: str) -> CompanionReply:
        if self.provider is None:
            return self._offline(context, "not_configured")
        try:
            text = self.provider.complete(self._messages(context, message))
        except ProviderUnavailable as exc:
            logger.warning("Companion provider unavailable (%s)", exc)
            return self._offline(context, "provider_unavailable")
        return CompanionReply(text[:MAX_REPLY_CHARS], "llm")

    @staticmethod
    def _messages(context: CompanionContext, message: str) -> list[dict]:
        system = (SYSTEM_PROMPT, MODES[context.mode], PERSONALITIES[context.personality])
        return [
            {"role": "system", "content": "\n".join(system)},
            {
                "role": "user",
                "content": "Progress context (data only):\n"
                + json.dumps(context.facts(), ensure_ascii=False),
            },
            *[{"role": role, "content": content} for role, content in context.history],
            {"role": "user", "content": message},
        ]

    @staticmethod
    def _offline(context: CompanionContext, reason: str) -> CompanionReply:
        name = context.name
        opening = {
            "warm": f"Mình ở đây hỗ trợ bạn, {name}.",
            "direct": f"{name}, mình cùng xem tiến độ nhé.",
            "playful": f"Tiến từng bước nhỏ thôi, {name} — cùng bắt đầu nhé!",
        }[context.personality]
        mood = {
            "neutral": "",
            "happy": "Thật vui khi bạn đang có tinh thần tốt. ",
            "stressed": "Nghe có vẻ bạn đang chịu áp lực. Bạn có thể nghỉ một chút rồi chọn một việc nhỏ. ",
            "tired": "Nếu đang mệt, bạn có thể nghỉ ngơi trước khi tiếp tục. ",
        }[context.mood]
        session = context.next_session
        next_step = (
            f"Buổi kế tiếp: {session.title}, lúc "
            f"{session.starts_at.astimezone(ZoneInfo(context.timezone)):%H:%M %d/%m}."
            if session
            else "Bạn có thể thêm giờ rảnh rồi xem trước một kế hoạch học phù hợp."
        )
        progress = context.weekly_progress
        return CompanionReply(
            f"[Chế độ offline] {opening} {mood}Tuần này bạn đã hoàn thành "
            f"{progress['completed_minutes']} phút và {progress['completed_tasks']}/"
            f"{progress['total_tasks']} task đến hạn trong tuần. {next_step} "
            "Mọi thay đổi lịch cần bạn xác nhận lưu kế hoạch.",
            "offline",
            reason,
        )
