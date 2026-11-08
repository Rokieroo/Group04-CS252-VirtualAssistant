"""Verify or drop (#101, spec 11.3, ADR 004): the four checks a shared resource
passes before any learner sees it, and the rule every read path applies.

Pure functions over what was fetched and the registries; the backend job
(``assistant.backend.catalog_verification``) records each result as one
append-only ``resource_verifications`` row.

A check ends in ``pass``, ``fail`` (definitive: the resource is ``rejected``),
``review`` (a person decides: unknown license, unsure labels, robots.txt) or
``error`` (the provider did not answer: no verdict, retried later).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.catalog.institutions import domain_of, matches_domain
from app.catalog.sources import Provider, Sources
from app.vetting.fetch import FetchResult
from app.vetting.policy import DomainPolicy, DomainTier

CHECKS = ("fetch", "domain", "license", "metadata")
FRESH_FOR = timedelta(days=30)  # older passes make a verified resource `stale`
PASS, FAIL, REVIEW, ERROR = "pass", "fail", "review", "error"

FORMATS = {"course", "book", "article", "reading", "video", "exercise"}
LEVELS = {"k12", "undergrad", "grad"}
LABEL_CONFIDENCE = 0.6  # Tag.needs_review below this
# FetchError codes that say nothing about the page itself.
_UNANSWERED = {"timeout", "network", "dns"}
# A person decides: a site asking bots to stay away, or a file too big to read.
_HUMAN = {"robots", "too_large"}


@dataclass(frozen=True)
class Check:
    name: str
    result: str  # pass | fail | review | error
    reason: str = ""  # short, log-safe code


@dataclass(frozen=True)
class Facts:
    """What the checks read about one resource; never page content."""

    url: str
    title: str
    provider: str  # a registry id for connector rows, else e.g. "web"
    license: str | None
    lang: str
    format: str
    level: str
    institution_domain: str | None = None  # of the catalog course's institution
    labels: tuple[float, ...] = ()  # confidence of each subject label


def fetch_check(fetched: FetchResult | None) -> Check:
    """``None``: the provider may not be fetched by a program (ADR 004 section 7)."""
    if fetched is None:
        return Check("fetch", REVIEW, "manual_check_required")
    if fetched.ok:
        return Check("fetch", PASS)
    if fetched.error in _UNANSWERED or (fetched.status or 0) >= 500 or fetched.status == 429:
        return Check("fetch", ERROR, fetched.error or f"http_{fetched.status}")
    if fetched.error in _HUMAN:
        return Check("fetch", REVIEW, fetched.error)
    return Check("fetch", FAIL, fetched.error or fetched.paywall or f"http_{fetched.status}")


def impersonated(url: str, domains: Iterable[str]) -> str | None:
    """A known domain the host spells out without belonging to it.

    ``ocw.mit.edu.example.com`` names ``mit.edu`` but is not MIT's: a fake page
    borrowing an institution's authority (ADR 004 section 4).
    """
    host = "." + domain_of(url) + "."
    return next(
        (
            d
            for d in domains
            if d and "." + d + "." in host and not matches_domain(url, d)
        ),
        None,
    )


def domain_check(
    facts: Facts,
    *,
    sources: Sources,
    policy: DomainPolicy,
    known_domains: Iterable[str],
    final_url: str = "",
) -> Check:
    for url in filter(None, (facts.url, final_url)):
        if policy.tier(url) is DomainTier.BLOCKED or policy.is_paywalled(url):
            return Check("domain", FAIL, "blocked_domain")
    claimed = sources.providers.get(facts.provider)
    if claimed is not None and not claimed.owns(facts.url):
        return Check("domain", FAIL, "provider_domain_mismatch")
    if facts.institution_domain and not matches_domain(facts.url, facts.institution_domain):
        return Check("domain", FAIL, "institution_domain_mismatch")
    if final_url and not (
        matches_domain(final_url, facts.url) or matches_domain(facts.url, final_url)
    ):
        return Check("domain", FAIL, "redirected_off_site")
    if found := impersonated(facts.url, known_domains):
        return Check("domain", FAIL, "impersonates:" + found)
    return Check("domain", PASS)


def license_check(facts: Facts, owner: Provider | None, sources: Sources) -> Check:
    """Only ids of ``catalog_sources.yaml``; a provider's own list when it has one."""
    if facts.license is None:
        return Check("license", REVIEW, "license_unknown")
    if facts.license not in sources.licenses:
        return Check("license", FAIL, "license_not_allowed")
    if owner is not None and facts.license not in owner.licenses:
        return Check("license", FAIL, "license_not_used_by_provider")
    return Check("license", PASS)


def metadata_check(facts: Facts) -> Check:
    if not facts.title.strip() or len(facts.title) > 300:
        return Check("metadata", FAIL, "bad_title")
    if not (facts.lang.isascii() and facts.lang.isalpha() and 2 <= len(facts.lang) <= 3):
        return Check("metadata", FAIL, "bad_language")
    if facts.format not in FORMATS:
        return Check("metadata", FAIL, "bad_format")
    if facts.level not in LEVELS:
        return Check("metadata", FAIL, "bad_level")
    if facts.labels and max(facts.labels) < LABEL_CONFIDENCE:
        return Check("metadata", REVIEW, "uncertain_subjects")
    return Check("metadata", PASS)


def decide(checks: Iterable[Check]) -> str | None:
    """The new status, or None to leave it (a person or a later run decides)."""
    results = {check.result for check in checks}
    if FAIL in results:
        return "rejected"
    if results == {PASS}:
        return "verified"
    return None


def _utc(moment: datetime | str) -> datetime:
    if isinstance(moment, str):  # raw SQL on SQLite returns text
        moment = datetime.fromisoformat(moment)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def latest_results(
    rows: Iterable[tuple[str, str, str, datetime | str]],
) -> dict[str, dict[str, tuple[str, datetime]]]:
    """resource id -> check -> (result, checked_at), from rows ordered newest first."""
    latest: dict[str, dict[str, tuple[str, datetime]]] = {}
    for resource_id, check, result, checked_at in rows:
        latest.setdefault(resource_id, {}).setdefault(check, (result, _utc(checked_at)))
    return latest


def is_current(latest: Mapping[str, tuple[str, datetime]], now: datetime) -> bool:
    """Every check's latest result is a pass from the last 30 days.

    The latest result wins, not any historic pass, so a read path fails closed
    even if a writer set ``verified`` without four fresh checks.
    """
    return all(
        check in latest
        and latest[check][0] == PASS
        and now - FRESH_FOR <= latest[check][1] <= now
        for check in CHECKS
    )
