"""The one interface every LLM vendor adapter implements (spec 6.1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class RetryableError(Exception):
    """Network error or HTTP 429/5xx: worth trying again, after ``retry_after`` seconds if known."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, system: str = "", json_schema: dict | None = None,
                 max_tokens: int = 1024, temperature: float = 0.2,
                 pdf: bytes | None = None) -> LLMResult:
        """``pdf`` is a PDF document the model reads along with the prompt (vision models)."""
