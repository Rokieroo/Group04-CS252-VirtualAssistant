"""The verification job and review decisions for shared resources (#101, ADR 004).

``verify_resource`` runs the four checks of ``app.catalog.verification`` on one
resource and appends one ``resource_verifications`` row per check, all with the
same ``checked_at``: every pass makes it ``verified``, a hard failure
``rejected``; an unsure license or label leaves it for a reviewer
(``review_queue``), an unanswered fetch for a later run.

The daily ``verify_catalog`` job first marks ``stale`` the verified resources
without four passes from the last 30 days, then verifies one batch, the ones
current roadmap nodes need first, and chains a job for the rest.
"""

import json
from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.catalog import verification as rules
from app.catalog.sources import Sources, load_sources
from app.vetting.document import readable_pages
from app.vetting.fetch import DomainThrottle, RateBudgetExceeded, SafeFetcher
from app.vetting.policy import default_policy

from .catalog_models import (
    Institution,
    NodeSubject,
    ResourceSubject,
    ResourceVerification,
)
from .catalog_repository import REMATCH, current_nodes
from .exercise_repository import harvest_catalog_exercises
from .jobs import NetworkDown, enqueue, handler
from .models import CatalogCourse, NodeResource, Resource

KIND = "verify_catalog"
CHECKED_BY = "job:" + KIND
BATCH = 20  # worst case 20 x 10 s fetches stays inside the 10-minute job lease
RETRY_AFTER = timedelta(hours=24)  # after a fetch nobody answered
REQUESTS_PER_HOUR = 1200  # per domain and worker, for every catalog job (#105)
BUDGET_WAIT = timedelta(hours=1)  # a domain's spent budget is whole again after this
OPEN = ("pending", "stale")  # statuses the job (re)verifies
ADMIN = "admin"  # check name of a reviewer's rejection


# --- what to verify, in order ------------------------------------------------------


def _last_run():
    """Each resource's latest run: the time all its check rows share."""
    return (
        select(
            ResourceVerification.resource_id,
            func.max(ResourceVerification.checked_at).label("at"),
        )
        .where(ResourceVerification.check_name.in_(rules.CHECKS))
        .group_by(ResourceVerification.resource_id)
        .subquery()
    )


def _in_last_run(result: str):
    """Ids of resources whose latest run has a ``result`` row."""
    last, row = _last_run(), aliased(ResourceVerification)
    return (
        select(row.resource_id)
        .join(last, and_(row.resource_id == last.c.resource_id, row.checked_at == last.c.at))
        .where(row.result == result)
    )


def _awaiting_review():
    """The last run asked a person, and its fetch was answered."""
    return and_(
        Resource.id.in_(_in_last_run(rules.REVIEW)),
        Resource.id.not_in(_in_last_run(rules.ERROR)),
    )


def _demand():
    """0: shown on a current node; 1: shares a label with one; 2: no node needs it."""
    shown = exists().where(
        NodeResource.resource_id == Resource.id,
        NodeResource.status == "shown",
        NodeResource.node_id.in_(current_nodes()),
    )
    wanted = select(NodeSubject.subject_id).where(
        NodeSubject.node_id.in_(current_nodes()),
        NodeSubject.confidence >= rules.LABEL_CONFIDENCE,
    )
    needed = exists().where(
        ResourceSubject.resource_id == Resource.id,
        ResourceSubject.confidence >= rules.LABEL_CONFIDENCE,
        ResourceSubject.subject_id.in_(wanted),
    )
    return case((shown, 0), (needed, 1), else_=2)


def due(db: Session, now: datetime, limit: int = BATCH) -> list[Resource]:
    """Pending or stale resources to check now, most needed first.

    Skips those waiting for a reviewer and those whose fetch went unanswered in
    the last day, so a chained job never re-reads the same rows.
    """
    last = _last_run()
    return list(
        db.scalars(
            select(Resource)
            .outerjoin(last, last.c.resource_id == Resource.id)
            .where(
                Resource.verification_status.in_(OPEN),
                or_(last.c.at.is_(None), last.c.at <= now - RETRY_AFTER),
                ~_awaiting_review(),
            )
            .order_by(_demand(), Resource.ingested_at.asc().nulls_first(), Resource.id)
            .limit(limit)
        )
    )


def mark_stale(db: Session, now: datetime) -> int:
    """Verified without four passes from the last 30 days -> ``stale`` (hidden)."""
    fresh = (
        select(ResourceVerification.resource_id)
        .where(
            ResourceVerification.check_name.in_(rules.CHECKS),
            ResourceVerification.result == rules.PASS,
            ResourceVerification.checked_at >= now - rules.FRESH_FOR,
        )
        .group_by(ResourceVerification.resource_id)
        .having(func.count(func.distinct(ResourceVerification.check_name)) == len(rules.CHECKS))
    )
    return db.execute(
        update(Resource)
        .where(Resource.verification_status == "verified", Resource.id.not_in(fresh))
        .values(verification_status="stale")
        .execution_options(synchronize_session=False)
    ).rowcount


# --- one resource ------------------------------------------------------------------


def known_domains(db: Session, sources: Sources) -> list[str]:
    """Institution and provider domains a fake page might borrow."""
    providers = [d for p in sources.providers.values() for d in p.domains]
    return sorted({*db.scalars(select(Institution.domain)), *providers})


def _facts(db: Session, resource: Resource) -> rules.Facts:
    course = db.get(CatalogCourse, resource.catalog_course_id) if resource.catalog_course_id else None
    institution = db.get(Institution, course.institution_id) if course and course.institution_id else None
    return rules.Facts(
        url=resource.url,
        title=resource.title,
        provider=resource.provider,
        license=resource.license,
        lang=resource.lang,
        format=resource.format or resource.kind,
        level=course.level if course else "undergrad",  # web rows: the read path's default
        institution_domain=institution.domain if institution else None,
        labels=tuple(
            db.scalars(
                select(ResourceSubject.confidence).where(ResourceSubject.resource_id == resource.id)
            )
        ),
    )


def _record(db, resource_id, check, now, by, **details):
    details = {"reason": check.reason, **details} if check.reason else details
    db.add(
        ResourceVerification(
            resource_id=resource_id,
            check_name=check.name,
            result=check.result,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            checked_at=now,
            checked_by=by,
        )
    )


def verify_resource(
    db: Session,
    resource_id: str,
    now: datetime,
    *,
    fetcher,
    sources: Sources | None = None,
    domains: list[str] | None = None,
) -> str:
    """Check one resource and record the run: verified | rejected | review | retry."""
    resource = db.get(Resource, resource_id)
    sources = sources or load_sources()
    facts = _facts(db, resource)
    registered = sources.provider_of(resource.url)
    # ADR 004 section 7: a provider whose terms forbid programs is checked by hand.
    fetched = None if registered and not registered.automated else fetcher.fetch(resource.url)
    checks = [
        rules.fetch_check(fetched),
        rules.domain_check(
            facts,
            sources=sources,
            policy=default_policy(),
            known_domains=domains if domains is not None else known_domains(db, sources),
            final_url=fetched.final_url if fetched else "",
        ),
        rules.license_check(
            facts, registered if registered and registered.use == "source" else None, sources
        ),
        rules.metadata_check(facts),
    ]
    if fetched is not None and fetched.status is not None:
        resource.http_status, resource.last_checked_at = fetched.status, now
    hashed = {}
    if fetched is not None and fetched.ok:
        resource.content_hash = hashed["content_hash"] = fetched.content_hash
    for check in checks:
        _record(db, resource.id, check, now, CHECKED_BY, **(hashed if check.name == "fetch" else {}))
    status = rules.decide(checks)
    if status is not None:
        resource.verification_status = status
        if status == "verified":
            # The page just checked is the evidence its exercises are quoted from (#115).
            harvest_catalog_exercises(
                db, resource.id, readable_pages(fetched), fetched.content_hash, now
            )
        return status
    return "retry" if any(c.result == rules.ERROR for c in checks) else "review"


@lru_cache(maxsize=4)
def _shared_throttle(rates: tuple[tuple[str, float], ...]) -> DomainThrottle:
    """One per worker process, so spacing and the hourly budget hold across the
    catalog jobs a worker runs back to back, not only within one of them."""
    return DomainThrottle(dict(rates), per_hour=REQUESTS_PER_HOUR)


def open_fetcher(sources: Sources) -> SafeFetcher:
    """Robots-aware, SSRF-safe, spaced per domain at the registry's rates."""
    return SafeFetcher(throttle=_shared_throttle(tuple(sorted(sources.rate_limits().items()))))


@handler(KIND)
def verify_catalog(db: Session, payload: dict, now: datetime) -> dict:
    """Mark expired passes stale, then verify one batch; chain a job for the rest.

    The chain counts what it verified, and its last job has the nodes still short
    of sources matched again (#105), so new sources reach learners without a wait.
    """
    stale = mark_stale(db, now)
    batch = due(db, now)
    sources = load_sources()
    domains = known_domains(db, sources)
    outcomes, deferred = Counter(), False
    with open_fetcher(sources) as fetcher:
        for resource in batch:
            try:
                outcomes[
                    verify_resource(
                        db, resource.id, now, fetcher=fetcher, sources=sources, domains=domains
                    )
                ] += 1
            except RateBudgetExceeded:
                deferred = True  # raised before the resource was touched
                break
    checked = sum(outcomes.values())
    if checked >= 3 and outcomes["retry"] == checked:
        raise NetworkDown  # rolled back, so nothing is recorded; retried with backoff
    verified = payload.get("verified", 0) + outcomes["verified"]
    if deferred or len(batch) == BATCH:
        later = now + BUDGET_WAIT if deferred else None
        enqueue(db, KIND, {"verified": verified}, now=now, run_after=later)
    elif verified:
        enqueue(db, REMATCH, now=now)
    return {"stale": stale, "checked": checked, "deferred": deferred, **outcomes}


# --- people ------------------------------------------------------------------------


def review_queue(db: Session, limit: int = 100) -> list[dict]:
    """Resources a person must decide on, most needed first, with their last run."""
    resources = list(
        db.scalars(
            select(Resource)
            .where(Resource.verification_status.in_(OPEN), _awaiting_review())
            .order_by(_demand(), Resource.id)
            .limit(limit)
        )
    )
    if not resources:
        return []
    last = {}
    for row in db.scalars(
        select(ResourceVerification)
        .where(
            ResourceVerification.resource_id.in_([r.id for r in resources]),
            ResourceVerification.check_name.in_(rules.CHECKS),
        )
        .order_by(ResourceVerification.checked_at.desc(), ResourceVerification.id.desc())
    ):
        last.setdefault(row.resource_id, {}).setdefault(row.check_name, row)
    return [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "provider": r.provider,
            "license": r.license,
            "verification_status": r.verification_status,
            "checks": [
                {
                    "check": name,
                    "result": row.result,
                    "reason": json.loads(row.details or "{}").get("reason", ""),
                    "checked_at": row.checked_at,
                }
                for name, row in sorted(last.get(r.id, {}).items())
            ],
        }
        for r in resources
    ]


def _resource(db: Session, resource_id: str) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise LookupError(resource_id)
    return resource


def verify_by_admin(
    db: Session, resource_id: str, *, reason: str, license: str | None, admin_id: str, now: datetime
) -> Resource:
    """A reviewer vouches for all four checks; every row keeps their id and reason.

    The read paths still need a fetched page (``content_hash``) and a license, so
    a resource without them cannot be verified by hand either.
    """
    resource = _resource(db, resource_id)
    if license is not None:
        if license not in load_sources().licenses:
            raise ValueError("unknown_license")
        resource.license = license
    if resource.license is None:
        raise ValueError("license_required")
    if resource.content_hash is None:
        raise ValueError("never_fetched")
    for name in rules.CHECKS:
        _record(db, resource.id, rules.Check(name, rules.PASS), now, admin_id, reason=reason)
    resource.verification_status = "verified"
    return resource


def reject_by_admin(
    db: Session, resource_id: str, *, reason: str, admin_id: str, now: datetime
) -> Resource:
    """Hidden everywhere at once, and a re-ingest never brings it back (ADR 004 s8)."""
    resource = _resource(db, resource_id)
    _record(db, resource.id, rules.Check(ADMIN, rules.FAIL), now, admin_id, reason=reason)
    resource.verification_status = "rejected"
    return resource
