"""Background jobs kept in the database, run by the worker (spec 14).

Slow work (syllabus parsing, resource search, link checks) leaves the HTTP request:
the API enqueues a job and the client polls GET /jobs/{id}. A table instead of a
broker keeps one moving part, and a job's side effects commit together with its
"done" status, so a crash never leaves half-recorded results.

Delivery is at least once: a worker that dies mid-job loses its lease and the job
runs again, so handlers must be safe to repeat.
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import Job

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict, datetime], Any]
HANDLERS: dict[str, Handler] = {}
MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=10)  # longer than any handler may run
RETRY_DELAY = timedelta(seconds=30)  # doubles after each failed attempt


class NetworkDown(Exception):
    """No link in a batch answered: our side is offline, so record nothing."""


def handler(kind: str):
    """Register ``fn(db, payload, now) -> JSON-serializable result`` for ``kind``."""

    def register(fn: Handler) -> Handler:
        if kind in HANDLERS:
            raise ValueError(f"job kind {kind!r} is already registered")
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(
    db: Session,
    kind: str,
    payload: dict | None = None,
    *,
    now: datetime,
    user_id: str | None = None,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
) -> Job | None:
    """Add a job in the caller's transaction. With ``dedupe_key``, return None when a
    job with that key already exists (e.g. today's cron run from another worker)."""
    if kind not in HANDLERS:
        raise ValueError(f"unknown job kind {kind!r}")
    job = Job(
        kind=kind,
        payload=json.dumps(payload or {}),
        user_id=user_id,
        dedupe_key=dedupe_key,
        run_after=run_after or now,
        created_at=now,
        updated_at=now,
    )
    if dedupe_key is None:
        db.add(job)
        db.flush()
        return job
    try:
        with db.begin_nested():
            db.add(job)
    except IntegrityError:
        return None
    return job


def run_once(sessions: sessionmaker, now: datetime) -> str | None:
    """Claim and run one due job; return its id, or None when nothing was due."""
    with sessions() as db:
        _expire_leases(db, now)
        job_id = _claim(db, now)
        db.commit()
    if job_id is None:
        return None
    with sessions() as db:
        job = db.get(Job, job_id)
        try:
            result = HANDLERS[job.kind](db, json.loads(job.payload), now)
            job.status, job.locked_at, job.updated_at = "done", None, now
            job.result = None if result is None else json.dumps(result)
            job.error = None
            db.commit()
        except Exception as exc:
            db.rollback()
            log.exception("job %s (%s) failed", job_id, job.kind)
            _retry_or_fail(db, job_id, type(exc).__name__, now)
            db.commit()
    return job_id


def _claim(db: Session, now: datetime) -> str | None:
    # Compare-and-set instead of SELECT ... FOR UPDATE SKIP LOCKED, so the same
    # code is safe with several workers on PostgreSQL and on SQLite.
    candidates = db.scalars(
        select(Job.id)
        .where(Job.status == "queued", Job.run_after <= now)
        .order_by(Job.run_after, Job.id)
        .limit(5)
    ).all()
    for job_id in candidates:
        claimed = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(
                status="running",
                attempts=Job.attempts + 1,
                locked_at=now,
                updated_at=now,
            )
        )
        if claimed.rowcount == 1:
            return job_id
    return None


def _expire_leases(db: Session, now: datetime) -> None:
    """Hand jobs of a crashed worker to the next one, or fail them when out of tries."""
    stale = (Job.status == "running", Job.locked_at <= now - LEASE)
    for retry, values in (
        (Job.attempts < MAX_ATTEMPTS, {"status": "queued", "run_after": now}),
        (Job.attempts >= MAX_ATTEMPTS, {"status": "failed", "error": "LeaseExpired"}),
    ):
        db.execute(
            update(Job)
            .where(*stale, retry)
            .values(locked_at=None, updated_at=now, **values)
        )


def _retry_or_fail(db: Session, job_id: str, error: str, now: datetime) -> None:
    job = db.get(Job, job_id)
    job.locked_at, job.updated_at, job.error = None, now, error
    if job.attempts >= MAX_ATTEMPTS:
        job.status = "failed"
    else:
        job.status = "queued"
        job.run_after = now + RETRY_DELAY * 2 ** (job.attempts - 1)
