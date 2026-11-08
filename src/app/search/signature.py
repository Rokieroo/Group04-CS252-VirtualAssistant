"""Cache key for a node's search results (spec 11.8)."""

from hashlib import sha256

from app.concepts import comparison_key


def node_signature(
    title: str, outcomes: list[str], level: str, language: str
) -> str:
    """Same key for every user studying the same node: the normalized title, its
    learning outcomes in any order, the learner level and the language.

    Built from course data only, never user data, because the cache is shared.
    """
    parts = [
        comparison_key(title),
        *sorted(comparison_key(outcome) for outcome in outcomes),
        comparison_key(level),
        language.strip().lower(),
    ]
    return sha256("\x1f".join(parts).encode()).hexdigest()
