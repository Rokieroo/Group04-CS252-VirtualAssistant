"""Daily upkeep jobs: re-check the links learners see (spec 11.7), verify the shared
catalog (#101, ``catalog_verification``), grow it where nodes lack sources (#105,
``catalog_jobs``) and prune old rows."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app import vetting

from . import catalog_jobs, catalog_verification  # register their job handlers
from .jobs import NetworkDown, enqueue, handler
from .models import Job, NodeResource, Resource, SearchCacheEntry

CHECK_EVERY = timedelta(hours=24)
DEAD_AFTER = 2  # consecutive dead checks before a link is removed (spec 11.7)
BATCH = 25  # links per job: worst case 25 x 2 requests x 5 s stays inside the lease
JOB_RETENTION = timedelta(days=30)
DAILY = ("check_links", "prune", catalog_verification.KIND)


def schedule_daily(db: Session, now: datetime) -> None:
    """Enqueue today's upkeep once; the dedupe key makes extra workers harmless."""
    today = now.date().isoformat()
    for kind in DAILY:
        enqueue(db, kind, now=now, dedupe_key=f"{kind}:{today}")
    catalog_jobs.schedule_nightly(db, now)


@handler("check_links")
def check_links(db: Session, payload: dict, now: datetime) -> dict:
    """Check one batch of shown links that are due; chain a job for the rest."""
    shown = select(NodeResource.resource_id).where(NodeResource.status == "shown")
    due = db.scalars(
        select(Resource)
        .where(
            Resource.id.in_(shown),
            or_(
                Resource.last_checked_at.is_(None),
                Resource.last_checked_at <= now - CHECK_EVERY,
            ),
        )
        .order_by(Resource.id)
        .limit(BATCH)
    ).all()
    statuses = [vetting.check_url(resource.url) for resource in due]
    if len(due) >= 3 and all(status is None for status in statuses):
        raise NetworkDown  # retried later with backoff
    removed = 0
    for resource, status in zip(due, statuses):
        resource.last_checked_at, resource.http_status = now, status
        alive = vetting.link_verdict(status)
        if alive:
            resource.failed_checks = 0
        elif alive is False:
            resource.failed_checks += 1
            if resource.failed_checks >= DEAD_AFTER:
                removed += _remove_everywhere(db, resource.id)
    if len(due) == BATCH:
        enqueue(db, "check_links", now=now)
    return {"checked": len(due), "removed": removed}


def _remove_everywhere(db: Session, resource_id: str) -> int:
    """A dead link leaves every node that shows it (spec 11.6)."""
    return db.execute(
        update(NodeResource)
        .where(NodeResource.resource_id == resource_id, NodeResource.status == "shown")
        .values(status="removed")
    ).rowcount


@handler("prune")
def prune(db: Session, payload: dict, now: datetime) -> dict:
    """Keep the cache and the job table from growing without bound."""
    cache = db.execute(
        delete(SearchCacheEntry).where(SearchCacheEntry.expires_at <= now)
    ).rowcount
    jobs = db.execute(
        delete(Job).where(
            Job.status.in_(("done", "failed")),
            Job.updated_at <= now - JOB_RETENTION,
        )
    ).rowcount
    return {"cache_entries": cache, "jobs": jobs}

