"""Vetting: checks and scores candidate resources (spec 6.1, 11.3-11.4)."""

from app.vetting.document import Document, read_document
from app.vetting.fetch import FetchResult, SafeFetcher, safe_fetch
from app.vetting.filters import Learner
from app.vetting.judge import Judgement
from app.vetting.links import check_url, is_public_url, link_verdict
from app.vetting.pipeline import Node, ScoredResource, Vetting, vet
from app.vetting.policy import DomainPolicy, DomainTier, domain_tier
from app.vetting.score import THRESHOLD, WEIGHTS

__all__ = [
    "THRESHOLD",
    "WEIGHTS",
    "Document",
    "DomainPolicy",
    "DomainTier",
    "FetchResult",
    "Judgement",
    "Learner",
    "Node",
    "SafeFetcher",
    "ScoredResource",
    "Vetting",
    "check_url",
    "domain_tier",
    "is_public_url",
    "link_verdict",
    "read_document",
    "safe_fetch",
    "vet",
]
