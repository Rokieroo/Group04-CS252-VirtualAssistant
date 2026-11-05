"""Opt-in text embeddings, behind the same vendor boundary as other AI calls.

The batching contract here is for gemini-embedding-001. Embedding 2 aggregates
multiple inputs, so it needs a different adapter rather than silently reusing this
one. See https://ai.google.dev/gemini-api/docs/embeddings .
"""

import math
import os
import ssl


def clean(value):
    return " ".join(str(value).split())


class GeminiEmbeddingEncoder:
    model = "gemini-embedding-001:semantic-similarity:v1"

    def __init__(self, api_key="", *, client=None):
        self.api_key = api_key
        self.client = client
        self.cache = {}

    def prepare(self, texts):
        import httpx
        from google import genai
        from google.genai import errors, types

        if self.client is None:
            import truststore

            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=30000,
                    client_args={
                        "verify": truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    },
                ),
            )
        missing = list(
            dict.fromkeys(clean(t) for t in texts if clean(t) not in self.cache)
        )
        for start in range(0, len(missing), 100):
            batch = missing[start : start + 100]
            try:
                response = self.client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=batch,
                    config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
                )
            except (errors.APIError, httpx.TransportError):
                raise RuntimeError("embedding_unavailable") from None
            vectors = [entry.values for entry in response.embeddings or []]
            if len(vectors) != len(batch):
                raise ValueError("invalid_embedding_count")
            checked = []
            for vector in vectors:
                if (
                    not vector
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v)
                        for v in vector
                    )
                    or sum(v * v for v in vector) <= 0
                ):
                    raise ValueError("invalid_embedding_values")
                norm = math.sqrt(sum(v * v for v in vector))
                checked.append([v / norm for v in vector])
            if len({len(v) for v in checked}) != 1:
                raise ValueError("inconsistent_embedding_dimensions")
            self.cache.update(zip(batch, checked, strict=True))

    def encode(self, value):
        return self.cache[clean(value)]


def get_embedding_encoder():
    """No key, model or opted-in Gemini provider: remain entirely offline."""
    if (
        os.getenv("LLM_PROVIDER", "fake") != "gemini"
        or os.getenv("EMBEDDING_MODEL", "") != "gemini-embedding-001"
        or not os.getenv("LLM_API_KEY", "").strip()
    ):
        return None
    return GeminiEmbeddingEncoder(os.environ["LLM_API_KEY"])
