"""Offline LLM and embedder for tests: no network, no cost."""
from __future__ import annotations

import math
import re
from hashlib import blake2b

from app.llm.base import Embedder, LLMClient, LLMResult


class HashingEmbedder(Embedder):
    """Bag of hashed words, L2-normalised: texts that share words point the same way.

    Lexical only, so it stands in for a real model in tests; never mix its vectors
    with another model's (``model`` tells them apart).
    """

    model = "hashing-256"
    dimensions = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"\w+", text.casefold()):
            digest = blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest, "big") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


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
