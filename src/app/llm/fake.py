"""Offline LLM for tests: no network, no cost."""
from __future__ import annotations

from app.llm.base import LLMClient, LLMResult


class FakeLLM(LLMClient):
    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls = 0

    def complete(self, prompt: str, *, system: str = "", json_schema: dict | None = None,
                 max_tokens: int = 1024, temperature: float = 0.2,
                 pdf: bytes | None = None) -> LLMResult:
        self.calls += 1
        text = next((answer for key, answer in self.responses.items() if key in prompt), "{}")
        return LLMResult(text=text, input_tokens=0, output_tokens=0, cost_usd=0.0)
