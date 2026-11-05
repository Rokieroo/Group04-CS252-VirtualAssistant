"""Google Gemini adapter. The only file allowed to import the google-genai SDK."""
from __future__ import annotations

import json
import logging
import threading
import time

from app.llm.base import Embedder, LLMClient, LLMResult, RetryableError

log = logging.getLogger("app.llm")

TIMEOUT_MS = 90_000  # a slower call counts as a failure, so the next model gets a turn
RETRY_DELAYS = (1, 3)  # seconds before retry 1 and retry 2
MAX_WAIT = 60  # a longer server-requested wait is a daily quota: retrying now cannot succeed
# USD per 1M tokens (input, output).
# shortcut: unknown models log cost 0, add their price here when the team switches model.
PRICES = {"gemini-3.8-flash": (0.75, 3.75)}  # standard tier, Oct 2026

__all__ = ["GeminiClient", "GeminiEmbedder", "RetryableError"]

EMBED_DIMENSIONS = 768  # enough for topic matching; a quarter of the default to store
EMBED_BATCH = 100  # texts per request, the API's limit
# The free tier counts each text as a request (100 a minute) and a 429 often names no
# wait, so the last retry waits out the minute instead of failing the job.
EMBED_RETRY_DELAYS = (5, MAX_WAIT)


def _sdk_client(api_key: str):
    import ssl

    import truststore
    from google import genai
    from google.genai import types

    # OS trust store, not certifi: antivirus/proxy TLS inspection on Windows
    # otherwise fails every call with CERTIFICATE_VERIFY_FAILED.
    verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=TIMEOUT_MS, client_args={"verify": verify}))


def _retry_after(error) -> float | None:
    """Seconds from the RetryInfo detail Gemini attaches to a 429, e.g. "42s"."""
    details = error.details.get("error", {}).get("details", []) if isinstance(error.details, dict) else []
    for detail in details:
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            try:
                return float(str(detail.get("retryDelay", "")).rstrip("s"))
            except ValueError:
                return None
    return None


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, models: list[str], thinking: str | None = None):
        self.api_key = api_key
        self.models = list(models)  # in priority order; the next one is used when one fails
        self.thinking = thinking  # e.g. "MINIMAL" for plain extraction; None = model default
        self._client = None  # created on first call so tests never need the SDK
        self._lock = threading.Lock()  # callers may share one client across threads

    def complete(self, prompt: str, *, system: str = "", json_schema: dict | None = None,
                 max_tokens: int = 1024, temperature: float = 0.2,
                 pdf: bytes | None = None) -> LLMResult:
        start = time.monotonic()
        models = list(self.models)
        for model in models:
            last = model == models[-1]
            try:
                # Only the last model retries: any other hands over at once (overload, timeout).
                text, input_tokens, output_tokens = self._with_retries(
                    model, last, prompt, system, json_schema, max_tokens, temperature, pdf)
                break
            except RetryableError as e:
                if last:
                    raise
                if (e.retry_after or 0) > MAX_WAIT:  # daily quota: skip it for this client's life
                    with self._lock:
                        if model in self.models and len(self.models) > 1:
                            self.models.remove(model)
                log.warning("provider=gemini model=%s unavailable (%s), trying the next model",
                            model, e)
        if json_schema is not None:
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Gemini trả về JSON không hợp lệ: {e}") from e

        in_price, out_price = PRICES.get(model, (0.0, 0.0))
        result = LLMResult(text, input_tokens, output_tokens,
                           (input_tokens * in_price + output_tokens * out_price) / 1_000_000)
        # Never log prompt or answer: they may contain student work.
        log.info("provider=gemini model=%s input_tokens=%d output_tokens=%d cost_usd=%.6f duration_ms=%d",
                 model, input_tokens, output_tokens, result.cost_usd,
                 (time.monotonic() - start) * 1000)
        return result

    def _with_retries(self, model: str, retry: bool, *args) -> tuple[str, int, int]:
        for delay in ((*RETRY_DELAYS, None) if retry else (None,)):
            try:
                return self._generate(model, *args)
            except RetryableError as e:
                wait = max(delay or 0, e.retry_after or 0)
                if delay is None or wait > MAX_WAIT:
                    raise
                time.sleep(wait)
        raise AssertionError("unreachable")  # the last attempt returns or raises

    def _generate(self, model: str, prompt: str, system: str, json_schema: dict | None,
                  max_tokens: int, temperature: float, pdf: bytes | None) -> tuple[str, int, int]:
        import httpx
        from google.genai import errors, types

        with self._lock:
            if self._client is None:
                self._client = _sdk_client(self.api_key)
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json" if json_schema is not None else None,
            response_json_schema=json_schema,
            thinking_config=(types.ThinkingConfig(thinking_level=self.thinking)
                             if self.thinking else None),
        )
        contents = ([types.Part.from_bytes(data=pdf, mime_type="application/pdf"), prompt]
                    if pdf is not None else prompt)
        try:
            resp = self._client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            if e.code == 429 or e.code >= 500:
                raise RetryableError(f"Gemini HTTP {e.code}", _retry_after(e)) from e
            raise
        except httpx.TransportError as e:
            raise RetryableError(f"Gemini network error: {type(e).__name__}: {e}") from e
        usage = getattr(resp, "usage_metadata", None)
        # Thinking tokens are billed as output.
        output_tokens = (
            (getattr(usage, "candidates_token_count", 0) or 0)
            + (getattr(usage, "thoughts_token_count", 0) or 0)
        ) if usage else 0
        prompt_tokens = (getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
        return (resp.text or "", prompt_tokens, output_tokens)


class GeminiEmbedder(Embedder):
    """Gemini text embeddings for semantic similarity, ``EMBED_DIMENSIONS`` long."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if self._client is None:
                self._client = _sdk_client(self.api_key)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            vectors += self._with_retries(texts[start:start + EMBED_BATCH])
        log.info("provider=gemini model=%s embedded=%d", self.model, len(texts))
        return vectors

    def _with_retries(self, texts: list[str]) -> list[list[float]]:
        for delay in (*EMBED_RETRY_DELAYS, None):
            try:
                return self._embed(texts)
            except RetryableError as e:
                wait = max(delay or 0, e.retry_after or 0)
                if delay is None or wait > MAX_WAIT:
                    raise
                time.sleep(wait)
        raise AssertionError("unreachable")  # the last attempt returns or raises

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        from google.genai import errors, types

        config = types.EmbedContentConfig(
            task_type="SEMANTIC_SIMILARITY", output_dimensionality=EMBED_DIMENSIONS)
        try:
            resp = self._client.models.embed_content(model=self.model, contents=texts,
                                                     config=config)
        except errors.APIError as e:
            if e.code == 429 or e.code >= 500:
                raise RetryableError(f"Gemini HTTP {e.code}", _retry_after(e)) from e
            raise
        except httpx.TransportError as e:
            raise RetryableError(f"Gemini network error: {type(e).__name__}: {e}") from e
        return [list(item.values) for item in resp.embeddings]
