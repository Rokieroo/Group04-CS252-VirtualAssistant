"""Deprecated: moved to app.companion (ADR 003). Re-exported so old imports keep working.

The database side of a chat turn now lives in services.companion_reply.
"""

from app.companion import (
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
    "companion_mode",
    "girlfriend_mode_allowed",
]
