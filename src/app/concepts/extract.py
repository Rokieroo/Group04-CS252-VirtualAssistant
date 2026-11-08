"""Backward-compatible facade for concept extraction (issues #9 and #50).

The Week 1 page-window pipeline now lives in ``from_pages.py`` and the shared
slug/normalization helpers in ``normalize.py``. Existing imports from
``app.concepts.extract`` keep working for the API, dev CLI and tests.
"""
from __future__ import annotations

from .from_pages import (  # noqa: F401
    BLOOM_LEVELS,
    CONSOLIDATE_PROMPT,
    CONSOLIDATE_SCHEMA,
    DECORATIVE,
    EXTRACT_PROMPT,
    EXTRACT_SCHEMA,
    MAX_CONCEPTS,
    PARALLEL,
    PROMPTS,
    STEP,
    WINDOW,
    _prompt,
    consolidate,
    extract_concepts,
    log,
    parse_concepts,
    save_concepts,
    windows,
)
from .normalize import SIMILAR_TITLE, merge, normalize, slugify

__all__ = [
    "BLOOM_LEVELS",
    "CONSOLIDATE_PROMPT",
    "CONSOLIDATE_SCHEMA",
    "DECORATIVE",
    "EXTRACT_PROMPT",
    "EXTRACT_SCHEMA",
    "MAX_CONCEPTS",
    "PARALLEL",
    "PROMPTS",
    "SIMILAR_TITLE",
    "STEP",
    "WINDOW",
    "consolidate",
    "extract_concepts",
    "log",
    "merge",
    "normalize",
    "parse_concepts",
    "save_concepts",
    "slugify",
    "windows",
]
