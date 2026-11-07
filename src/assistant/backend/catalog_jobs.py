"""Grow the shared catalog where learners need it (#105).

Each night ``fill_gaps`` matches the nodes left ``insufficient`` again, then
queues one ``ingest_catalog`` job per connector and subject those nodes still
lack. An ingest that stores new resources queues ``verify_catalog`` (#101), and
the end of that chain matches the gap nodes once more::

    fill_gaps -> ingest_catalog (connector x subject) -> verify_catalog ... -> rematch_sources

Once a month every connector is read again for every subject. One job reads
one connector for one subject: it fits inside the job lease, a provider that
fails stops only its own jobs, and the dedupe key (connector, subject, day or
month) fetches a subject at most once per period. Requests are spaced and
capped per domain by the worker's shared throttle
(``catalog_verification.open_fetcher``), and a job stops reading at
``RUN_BUDGET``; what it left unread is read by the next run.
"""

import time
from datetime import datetime
from datetime import time as clock

from sqlalchemy.orm import Session

from app.catalog.connectors import CONNECTORS, ConnectorError, build_connectors
from app.catalog.sources import load_sources
from app.catalog.taxonomy import subjects as taxonomy

from . import catalog_verification
from .catalog_ingest import ingest
from .catalog_repository import gap_subjects, rematch_insufficient
from .jobs import LEASE, enqueue, handler

FILL = "fill_gaps"
INGEST = "ingest_catalog"
NIGHT = clock(19, 0)  # UTC: 02:00 in Vietnam, when learners are asleep
RUN_BUDGET = LEASE.total_seconds() * 0.8  # seconds; the job commits before its lease ends


def tonight(now: datetime) -> datetime:
    """Today at ``NIGHT``, or ``now`` once that has passed."""
    return max(now, datetime.combine(now.date(), NIGHT, now.tzinfo))


def broad_subjects() -> list[str]:
    """Subjects below the root fields ("ct", "db", ...); each covers its topics."""
    return [row["id"] for row in taxonomy() if row.get("depth") == 2]


def schedule_nightly(db: Session, now: datetime) -> None:
    """Queue tonight's gap filling and this month's full re-read of each connector.

    Called every day: the dedupe keys make repeats no-ops, so a worker that was
    down on the 1st still runs the month's re-read. A finished job's key is
    pruned only after 30 days, by when the month in it has passed.
    """
    night = tonight(now)
    enqueue(db, FILL, now=now, dedupe_key=f"{FILL}:{now.date().isoformat()}", run_after=night)
    month = now.strftime("%Y-%m")
    for subject in broad_subjects():
        for connector in CONNECTORS:
            queue_ingest(db, connector, subject, now, period=month, run_after=night)


def queue_ingest(
    db: Session,
    connector: str,
    subject: str,
    now: datetime,
    *,
    period: str,
    run_after: datetime | None = None,
) -> bool:
    """Queue one read of ``connector`` for ``subject``; False if this period has one."""
    job = enqueue(
        db,
        INGEST,
        {"connector": connector, "subject": subject},
        now=now,
        dedupe_key=f"{INGEST}:{connector}:{subject}:{period}",
        run_after=run_after,
    )
    return job is not None


@handler(FILL)
def fill_gaps(db: Session, payload: dict, now: datetime) -> dict:
    """Match the gap nodes again, then queue ingests for the labels they still lack."""
    matched = rematch_insufficient(db, now)
    gaps = gap_subjects(db)
    today = now.date().isoformat()
    queued = sum(
        queue_ingest(db, connector, subject, now, period=today)
        for subject in gaps
        for connector in CONNECTORS
    )
    return {**matched, "subjects": gaps, "ingest_jobs": queued}


@handler(INGEST)
def ingest_catalog(db: Session, payload: dict, now: datetime) -> dict:
    """Read one connector for one subject; queue verification of what is new.

    A provider that fails is reported in the result, not raised: retrying at
    once would not help, and the next scheduled run reads it again.
    """
    name, subject = payload["connector"], payload["subject"]
    sources = load_sources()
    with catalog_verification.open_fetcher(sources) as fetcher:
        try:
            [connector] = build_connectors(fetcher, [name], sources)
        except ConnectorError as exc:
            return {"connector": name, "subject": subject, "error": exc.reason}
        report = ingest(
            db,
            connector,
            [subject],
            now=now,
            sources=sources,
            deadline=time.monotonic() + RUN_BUDGET,
        )
    if report.created["resources"]:
        enqueue(db, catalog_verification.KIND, now=now)
    return {
        "connector": name,
        "subject": subject,
        "records": report.records,
        "created": dict(report.created),
        "updated": report.updated,
        "skipped": dict(report.skipped),
        "error": report.error,
    }
