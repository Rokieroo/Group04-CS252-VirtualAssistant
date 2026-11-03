"""Concept extraction and topic normalization (issues #9 and #50).

Prompts live in ``prompts/`` with a version in the file name. The Week 1
page-window pipeline is in ``from_pages.py``; shared slug and duplicate-merge
rules are in ``normalize.py``. ``extract.py`` remains as a compatibility facade.
"""
from .extract import (
    BLOOM_LEVELS,
    CONSOLIDATE_PROMPT,
    CONSOLIDATE_SCHEMA,
    DECORATIVE,
    EXTRACT_PROMPT,
    EXTRACT_SCHEMA,
    MAX_CONCEPTS,
    PARALLEL,
    PROMPTS,
    SIMILAR_TITLE,
    STEP,
    WINDOW,
    consolidate,
    extract_concepts,
    log,
    merge,
    normalize,
    parse_concepts,
    save_concepts,
    windows,
)
from .normalize import TopicIn, comparison_key, normalize_topics, slugify

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
    "TopicIn",
    "comparison_key",
    "consolidate",
    "extract_concepts",
    "log",
    "merge",
    "normalize",
    "normalize_topics",
    "parse_concepts",
    "save_concepts",
    "slugify",
    "windows",
]
