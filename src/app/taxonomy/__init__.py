"""Taxonomy: one set of subject labels for roadmap nodes and catalog resources (issue #99).

``tree`` reads and validates ``data/catalog/subjects.yaml``; ``rules`` is the cheap
first stage of tagging; ``tagger`` runs the whole cascade (rules, embeddings, LLM).
"""

from app.taxonomy.rules import find_course_codes, fold
from app.taxonomy.tagger import (
    REVIEW_CONFIDENCE,
    NodeText,
    ResourceText,
    Tag,
    Tagger,
    Tagging,
    parse_answer,
)
from app.taxonomy.tree import Subject, Taxonomy, TaxonomyError, load_taxonomy

__all__ = [
    "REVIEW_CONFIDENCE",
    "NodeText",
    "ResourceText",
    "Subject",
    "Tag",
    "Tagger",
    "Tagging",
    "Taxonomy",
    "TaxonomyError",
    "find_course_codes",
    "fold",
    "load_taxonomy",
    "parse_answer",
]
