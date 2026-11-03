"""Hard filters that run before any scoring (spec 11.3); a dropped link is never shown.

Each check returns a short, log-safe reason code, or None when the resource passes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.vetting.document import Document
from app.vetting.fetch import FetchResult

__all__ = ["Deduper", "Learner", "content_failure", "fetch_failure"]

# The only paywall reason "allow paid resources" lifts; a login wall stays a wall.
_PAID = "known_domain"


@dataclass(frozen=True)
class Learner:
    """Who the resources are for: preferences and level, never personal data.

    ``k12`` learners also need their candidates searched with ``safe=True``
    (SafeSearch, spec 11.3 step 4); vetting adds the adult-label check.
    """

    langs: tuple[str, ...] = ("vi", "en")
    level: str = ""
    k12: bool = False
    allow_paid: bool = False


def fetch_failure(fetched: FetchResult, learner: Learner) -> str | None:
    """Step 1 (verify or drop) and step 5 (free) on the fetch result."""
    if fetched.error:
        return fetched.error
    if fetched.status != 200:
        return f"http_{fetched.status}"
    if fetched.paywall and not (learner.allow_paid and fetched.paywall == _PAID):
        return fetched.paywall
    return None


def content_failure(document: Document, learner: Learner) -> str | None:
    """Steps 3-4: something to read, in an allowed language, fit for the learner's age."""
    if not document.text:
        return "no_text"
    if document.lang not in learner.langs:
        return "language"
    if learner.k12 and document.adult:
        return "age"
    return None


class Deduper:
    """Step 6: one resource per canonical URL, video id and content hash."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def seen(self, *keys: str) -> bool:
        """True when any key was seen before; all keys are remembered either way."""
        keys_set = {key for key in keys if key}
        duplicate = not keys_set.isdisjoint(self._seen)
        self._seen |= keys_set
        return duplicate
