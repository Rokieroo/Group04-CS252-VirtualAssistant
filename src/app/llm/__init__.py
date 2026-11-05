"""The only module that talks to an LLM vendor. Pick one with LLM_PROVIDER (see .env.example)."""
from __future__ import annotations

import os

from app.llm.base import Embedder, LLMClient, LLMResult, RetryableError
from app.llm.fake import FakeLLM, HashingEmbedder
from app.llm.metered import MeteredLLM

# Tried in order: the next model is used when one is over quota or unavailable.
DEFAULT_GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")  # organise concepts
DEFAULT_VISION_MODELS = ("gemini-3.1-flash-lite",)  # read PDF pages as images
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

__all__ = ["Embedder", "FakeLLM", "HashingEmbedder", "LLMClient", "LLMResult", "MeteredLLM",
           "RetryableError", "get_client", "get_embedder", "get_vision_client"]


def get_embedder() -> Embedder:
    """Text embeddings (subject tagging, hybrid retrieval): LLM_EMBEDDING_MODEL, one model.

    One model, not a fallback list: vectors of different models cannot be compared.
    """
    provider = os.environ.get("LLM_PROVIDER", "fake").strip().lower() or "fake"
    if provider == "fake":
        return HashingEmbedder()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(f"Thiếu LLM_API_KEY (LLM_PROVIDER={provider}). Điền key vào .env.")
    if provider == "gemini":
        from app.llm.gemini import GeminiEmbedder

        model = os.environ.get("LLM_EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL
        return GeminiEmbedder(api_key, model)
    raise ValueError(f"LLM_PROVIDER không hỗ trợ: '{provider}'. Dùng: fake, gemini.")


def get_client() -> LLMClient:
    """Text work (concept organisation and output): LLM_MODEL, a comma list tried in order."""
    return _client("LLM_MODEL", DEFAULT_GEMINI_MODELS)


def get_vision_client() -> LLMClient:
    """Reads PDF pages visually (diagrams, tables, scans): LLM_VISION_MODEL, a comma list."""
    # Minimal thinking: it transcribes what it sees; reasoning is the concept model's job.
    return _client("LLM_VISION_MODEL", DEFAULT_VISION_MODELS, thinking="MINIMAL")


def _client(model_variable: str, default_models: tuple[str, ...],
            thinking: str | None = None) -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "fake").strip().lower() or "fake"
    if provider == "fake":
        return FakeLLM()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(f"Thiếu LLM_API_KEY (LLM_PROVIDER={provider}). Điền key vào .env.")
    if provider == "gemini":
        from app.llm.gemini import GeminiClient

        models = [m.strip() for m in os.environ.get(model_variable, "").split(",") if m.strip()]
        return GeminiClient(api_key, models or list(default_models), thinking)
    raise ValueError(f"LLM_PROVIDER không hỗ trợ: '{provider}'. Dùng: fake, gemini.")
