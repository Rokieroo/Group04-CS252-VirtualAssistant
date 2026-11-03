"""Caches.

ReportCache: small, bounded, per-process progress cache; no cross-user keys.
Search cache: search results in the database, shared by every user and worker that
studies the same node for 7 days (spec 11.8). Keys are node signatures built from
course data only (app.search.node_signature), so no user data is shared.
"""

import json
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import SearchCacheEntry

SEARCH_TTL = timedelta(days=7)


class ReportCache:
    def __init__(self, ttl_seconds=10, max_entries=128):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._items = OrderedDict()
        self._lock = Lock()
        self._generation = 0

    @property
    def generation(self):
        with self._lock:
            return self._generation

    def get(self, key):
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= monotonic():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value.model_copy(deep=True)

    def put(self, key, value, generation):
        with self._lock:
            if generation != self._generation:
                return  # A concurrent commit invalidated the query while it ran.
            self._items[key] = (
                monotonic() + self.ttl_seconds,
                value.model_copy(deep=True),
            )
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self):
        with self._lock:
            self._generation += 1
            self._items.clear()


def cached_search(db: Session, signature: str, now: datetime) -> Any | None:
    """The stored results for ``signature``, or None when missing or expired."""
    entry = db.get(SearchCacheEntry, signature)
    if entry is None or entry.expires_at <= now:
        return None
    return json.loads(entry.payload)


def store_search(db: Session, signature: str, results: Any, now: datetime) -> None:
    """Keep ``results`` for SEARCH_TTL. Expired rows are pruned by the daily job."""
    payload, expires_at = json.dumps(results), now + SEARCH_TTL
    entry = db.get(SearchCacheEntry, signature)
    if entry is not None:
        entry.payload, entry.expires_at = payload, expires_at
        return
    try:
        with db.begin_nested():
            db.add(
                SearchCacheEntry(
                    signature=signature, payload=payload, expires_at=expires_at
                )
            )
    except IntegrityError:
        pass  # Another worker stored the same node at the same time; keep theirs.
