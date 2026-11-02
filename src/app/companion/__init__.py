"""Companion: motivating, grounded chat by mode and personality (spec 6.1)."""

from app.companion.chat import (
    ChatProvider,
    Companion,
    CompanionContext,
    CompanionReply,
    NextSession,
    PendingTask,
    ProviderUnavailable,
)
from app.companion.persona import (
    MODES,
    PERSONALITIES,
    SYSTEM_PROMPT,
    companion_mode,
    girlfriend_mode_allowed,
)

__all__ = [
    "MODES",
    "PERSONALITIES",
    "SYSTEM_PROMPT",
    "ChatProvider",
    "Companion",
    "CompanionContext",
    "CompanionReply",
    "NextSession",
    "PendingTask",
    "ProviderUnavailable",
    "companion_mode",
    "girlfriend_mode_allowed",
]
