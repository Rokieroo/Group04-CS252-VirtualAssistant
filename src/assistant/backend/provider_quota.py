"""Daily call quotas for the external search providers (issue #161).

``PROVIDER_DAILY_QUOTA`` caps each provider's calls per UTC day across all learners
and ``PROVIDER_LEARNER_DAILY_QUOTA`` per learner. Both read ``name=calls`` pairs,
e.g. ``youtube=90,web=2000``; a provider left out is unlimited. Calls are counted
from ``search_runs``, the rows the cost dashboard reads, so both always agree.
"""

import os
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import SearchRun

DAILY_ENV = "PROVIDER_DAILY_QUOTA"
LEARNER_ENV = "PROVIDER_LEARNER_DAILY_QUOTA"


def parse_limits(name: str, value: str) -> dict[str, int]:
    """``"youtube=90, web=2000"`` -> ``{"youtube": 90, "web": 2000}``."""
    limits = {}
    for pair in filter(None, (part.strip() for part in value.split(","))):
        provider, _, calls = (piece.strip() for piece in pair.partition("="))
        if not provider or not calls.isdigit():
            raise ValueError(f"{name} must look like 'youtube=90,web=2000', got {pair!r}")
        limits[provider] = int(calls)
    return limits


def remaining_calls(db: Session, user_id: str, now: datetime) -> dict[str, int]:
    """Calls each limited provider may still make today for ``user_id``.

    shortcut: workers read the count before their own calls are logged, so searches
    running at the same moment can overshoot by one search's calls; take a row lock
    per provider if a vendor ever bills overage.
    """
    daily = parse_limits(DAILY_ENV, os.getenv(DAILY_ENV, ""))
    per_learner = parse_limits(LEARNER_ENV, os.getenv(LEARNER_ENV, ""))
    limited = daily.keys() | per_learner.keys()
    if not limited:
        return {}
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = {
        provider: (everyone, mine)
        for provider, everyone, mine in db.execute(
            select(
                SearchRun.provider,
                func.count(),
                func.coalesce(func.sum(case((SearchRun.user_id == user_id, 1), else_=0)), 0),
            )
            .where(SearchRun.created_at >= today, SearchRun.provider.in_(limited))
            .group_by(SearchRun.provider)
        )
    }
    remaining = {}
    for provider in limited:
        everyone, mine = used.get(provider, (0, 0))
        caps = [daily[provider] - everyone] if provider in daily else []
        if provider in per_learner:
            caps.append(per_learner[provider] - mine)
        remaining[provider] = max(0, min(caps))
    return remaining
