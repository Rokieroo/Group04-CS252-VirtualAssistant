"""What the HTTP search providers share (spec 11.2): plain text, secret-free error
labels, and which failures are worth a retry."""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

_RETRY_STATUS = {429, 500, 502, 503, 504}
_TAG_RE = re.compile(r"<[^>]+>")


def plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def error_code(exc: Exception) -> str:
    """A short, secret-free error label for logs and ``search_runs``."""

    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "network"
    return type(exc).__name__


def transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return isinstance(exc, httpx.TransportError)


__all__ = ["error_code", "plain_text", "transient"]
