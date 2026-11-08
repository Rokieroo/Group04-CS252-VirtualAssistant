"""Catalog health behind the admin dashboard (#105, beside the cost report of #69).

Where learners lack sources (insufficient nodes per subject), what the catalog
holds (resources per verification status), which connectors failed, which links
died, and how the gap count moved after each ``fill_gaps`` or re-match run.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .catalog_jobs import FILL, INGEST
from .catalog_repository import REMATCH, gap_subjects, insufficient_nodes
from .maintenance import DEAD_AFTER
from .models import Job, Resource, Subject

DEAD_SHOWN = 20  # dead links listed by name; the rest are only counted
RUNS_SHOWN = 14  # recent gap runs, about two weeks of nights


def _result(job: Job) -> dict:
    return json.loads(job.result) if job.result else {}


def _connectors(db: Session, since: datetime) -> list[dict]:
    """Per connector: runs, failed runs and the last failure in the window."""
    summary = {}
    for job in db.scalars(
        select(Job)
        .where(Job.kind == INGEST, Job.status.in_(("done", "failed")), Job.updated_at >= since)
        .order_by(Job.updated_at)
    ):
        name = json.loads(job.payload or "{}").get("connector", "?")
        outcome = _result(job)
        error = job.error if job.status == "failed" else outcome.get("error")
        row = summary.setdefault(
            name,
            {"connector": name, "runs": 0, "errors": 0, "created": 0,
             "last_run_at": None, "last_error": None},
        )
        row["runs"] += 1
        row["created"] += outcome.get("created", {}).get("resources", 0)
        row["last_run_at"] = job.updated_at
        if error:
            row["errors"] += 1
            row["last_error"] = error
    return sorted(summary.values(), key=lambda row: row["connector"])


def catalog_health(db: Session, *, now: datetime, days: int) -> dict:
    since = now - timedelta(days=days)
    names = dict(db.execute(select(Subject.id, Subject.name)).all())
    dead = Resource.failed_checks >= DEAD_AFTER
    runs = db.scalars(
        select(Job)
        .where(Job.kind.in_((FILL, REMATCH)), Job.status == "done")
        .order_by(desc(Job.updated_at))
        .limit(RUNS_SHOWN)
    )
    return {
        "days": days,
        "insufficient_nodes": db.scalar(
            select(func.count()).select_from(insufficient_nodes().subquery())
        ),
        "gaps": [
            {"subject_id": subject, "name": names.get(subject, subject), "nodes": count}
            for subject, count in sorted(gap_subjects(db).items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "resources": dict(
            db.execute(
                select(Resource.verification_status, func.count())
                .where(Resource.source_connector.is_not(None))
                .group_by(Resource.verification_status)
            ).all()
        ),
        "connectors": _connectors(db, since),
        "dead_links": db.scalar(select(func.count()).select_from(Resource).where(dead)),
        "dead": [
            {"id": r.id, "title": r.title, "url": r.url, "http_status": r.http_status,
             "last_checked_at": r.last_checked_at}
            for r in db.scalars(
                select(Resource).where(dead).order_by(desc(Resource.last_checked_at)).limit(DEAD_SHOWN)
            )
        ],
        "gap_runs": [
            {"kind": job.kind, "at": job.updated_at,
             "insufficient_before": _result(job).get("insufficient_before", 0),
             "insufficient_after": _result(job).get("insufficient_after", 0),
             "ingest_jobs": _result(job).get("ingest_jobs", 0)}
            for job in runs
        ],
    }
