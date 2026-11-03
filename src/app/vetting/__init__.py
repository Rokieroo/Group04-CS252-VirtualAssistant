"""Vetting: checks and scores candidate resources (spec 6.1, 11.3). Phase 2."""

from app.vetting.fetch import FetchResult, SafeFetcher, safe_fetch
from app.vetting.links import check_url, is_public_url, link_verdict
from app.vetting.policy import DomainPolicy, DomainTier, domain_tier

__all__ = [
    "DomainPolicy",
    "DomainTier",
    "FetchResult",
    "SafeFetcher",
    "check_url",
    "domain_tier",
    "is_public_url",
    "link_verdict",
    "safe_fetch",
]
