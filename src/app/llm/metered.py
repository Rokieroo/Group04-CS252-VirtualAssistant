"""Count what one unit of work spends on the LLM (spec 14: cost per search)."""
from __future__ import annotations

import threading

from app.llm.base import LLMClient, LLMResult


class MeteredLLM(LLMClient):
    """Wraps a client and adds up calls, tokens and cost; failed calls are not billed."""

    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self._lock = threading.Lock()  # callers may share one meter across threads

    def complete(self, prompt: str, **options) -> LLMResult:
        result = self.inner.complete(prompt, **options)
        with self._lock:
            self.calls += 1
            self.input_tokens += result.input_tokens
            self.output_tokens += result.output_tokens
            self.cost_usd += result.cost_usd
        return result
