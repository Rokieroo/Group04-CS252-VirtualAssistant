"""Store connector output in the shared catalog (#98, ADR 004 sections 5 and 8).

``upsert_records`` is idempotent: courses key on ``(provider, external_id)``,
resources on ``canonical_url`` and units on ``(course, position)``, so a second
run over the same records creates no row. A new resource is always ``pending``;
an existing one keeps its verification status, so a ``rejected`` (taken down)
source is never brought back.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select

from app.catalog.connectors import (
    CatalogConnector,
    CatalogRecord,
    ConnectorError,
    check_record,
)
from app.catalog.demand import SyllabusDemand, node_subjects
from app.catalog.institutions import domain_of
from app.catalog.sources import Sources, load_sources
from app.catalog.taxonomy import Tag, save_tags, tag_records
from app.search.service import canonical_url

from .catalog_models import CatalogCourse, CatalogUnit, ResourceSubject
from .models import Assessment, Course, LearningOutcome, Resource, Syllabus

CANDIDATE_STATUSES = ("pending", "verified")
CURATED = "rule:curated"  # labels a reviewer wrote in a manual YAML file


@dataclass
class IngestReport:
    connector: str
    records: int = 0
    created: Counter = field(default_factory=Counter)  # courses | resources | units
    updated: int = 0
    skipped: Counter = field(default_factory=Counter)  # reason -> records
    error: str | None = None


def _assign(row, values: dict) -> bool:
    """Set the values that differ; True if any did."""
    changed = [key for key, value in values.items() if getattr(row, key) != value]
    for key in changed:
        setattr(row, key, values[key])
    return bool(changed)


class _Upsert:
    """One run of one connector: the rows it wrote and the ones to tag."""

    def __init__(self, db, connector: str, now: datetime, report: IngestReport):
        self.db, self.connector, self.now, self.report = db, connector, now, report
        self.tag_rows: list[dict] = []
        self.curated: list[tuple[Resource, tuple[str, ...], str]] = []

    def course(self, record: CatalogRecord) -> CatalogCourse:
        values = {
            "code": record.code,
            "title": record.title,
            "level": record.level,
            "language": record.language,
            "license": record.license,
            "url": record.url,
            "year": record.year,
        }
        same = CatalogCourse.provider == record.provider
        row = self.db.scalar(
            select(CatalogCourse).where(same, CatalogCourse.external_id == record.external_id)
        )
        if row is not None:
            self.report.updated += _assign(row, values)
            return row
        # A course both listed by hand and found by its connector has two keys but
        # one row; only the key that created it updates its metadata.
        row = self.db.scalar(select(CatalogCourse).where(same, CatalogCourse.url == record.url))
        if row is None:
            row = CatalogCourse(provider=record.provider, external_id=record.external_id, **values)
            self.db.add(row)
            self.db.flush()
            self.report.created["courses"] += 1
        return row

    def resource(self, record, course, *, url, title, fmt, tag_fields) -> Resource:
        values = {
            "title": title,
            "provider": record.provider,
            "kind": fmt,
            "format": fmt,
            "lang": record.language,
            "license": record.license,
            "is_free": record.is_free,
            "domain": domain_of(url),
            "catalog_course_id": course.id,
        }
        row = self.db.scalar(select(Resource).where(Resource.canonical_url == canonical_url(url)))
        retag = False
        if row is None:
            row = Resource(
                url=url,
                canonical_url=canonical_url(url),
                source_connector=self.connector,
                ingested_at=self.now,
                verification_status="pending",
                **values,
            )
            self.db.add(row)
            self.db.flush()
            self.report.created["resources"] += 1
            retag = True
        elif row.source_connector == self.connector:
            # The connector that created a row owns its metadata; web-search rows and
            # rows of other connectors keep theirs. The status is never reset.
            retag = _assign(row, values)
            self.report.updated += retag
        content = " ".join(str(v) for v in tag_fields.values() if v)
        if record.subjects:
            # A reviewer's labels describe the page, whoever stored its row.
            self.curated.append((row, record.subjects, content))
        elif retag:
            # Only new or changed rows: re-tagging would undo `ai tag-catalog`'s
            # embedding and LLM labels with the offline ones.
            self.tag_rows.append({"id": row.id, **tag_fields})
        return row

    def unit(self, course: CatalogCourse, position: int, title: str, resource: Resource):
        row = self.db.scalar(
            select(CatalogUnit).where(
                CatalogUnit.course_id == course.id, CatalogUnit.position == position
            )
        )
        values = {"title": title, "resource_id": resource.id}
        if row is None:
            self.db.add(CatalogUnit(course_id=course.id, position=position, **values))
            self.report.created["units"] += 1
        elif _assign(row, values):
            self.report.updated += 1

    def tag(self):
        tag_records(self.db, "resource", self.tag_rows)
        stored = defaultdict(set)
        for resource_id, subject in self.db.execute(
            select(ResourceSubject.resource_id, ResourceSubject.subject_id).where(
                ResourceSubject.method == CURATED,
                ResourceSubject.resource_id.in_([row.id for row, _, _ in self.curated]),
            )
        ):
            stored[resource_id].add(subject)
        for row, labels, content in self.curated:
            if stored[row.id] != set(labels):
                tags = [Tag(subject, 0.95, CURATED) for subject in labels]
                save_tags(self.db, "resource", row.id, tags, content)


def upsert_records(
    db,
    records,
    *,
    connector: str,
    now: datetime,
    sources: Sources | None = None,
    report: IngestReport | None = None,
) -> IngestReport:
    """Validate and store ``records``; the caller commits.

    Records that fail :func:`check_record` are counted in ``skipped``, never stored.
    """
    sources = sources or load_sources()
    report = report or IngestReport(connector)
    run = _Upsert(db, connector, now, report)
    try:
        for record in records:
            report.records += 1
            reason = check_record(record, sources)
            if reason:
                report.skipped[reason] += 1
                continue
            _store(run, record)
    finally:
        # Also when the provider fails midway: a stored row left untagged would
        # never be tagged, since the next run finds it unchanged.
        run.tag()
    return report


def _store(run: _Upsert, record: CatalogRecord) -> None:
    course = run.course(record)
    context = {"code": record.code or "", "department": record.department}
    run.resource(
        record,
        course,
        url=record.url,
        title=record.title,
        fmt=record.format,
        tag_fields={"title": record.title, **context, "description": record.description},
    )
    for unit in record.units:
        resource = run.resource(
            record,
            course,
            url=unit.url,
            title=unit.title,
            fmt=unit.format,
            tag_fields={"title": unit.title, "course": record.title, **context},
        )
        run.unit(course, unit.position, unit.title, resource)


def ingest(
    db,
    connector: CatalogConnector,
    subjects,
    *,
    now: datetime,
    since: datetime | None = None,
    sources: Sources | None = None,
) -> IngestReport:
    """Run one connector; a provider that cannot be read is reported, not raised.

    Records read before the failure stay staged: the upsert is idempotent, so the
    next run simply goes over them again.
    """
    report = IngestReport(connector.name)
    try:
        upsert_records(
            db,
            connector.fetch(subjects, since),
            connector=connector.name,
            now=now,
            sources=sources,
            report=report,
        )
    except ConnectorError as exc:
        report.error = exc.reason
    return report


def syllabus_demand(db, syllabus_id: str) -> SyllabusDemand | None:
    syllabus = db.get(Syllabus, syllabus_id)
    if syllabus is None:
        return None
    course = db.get(Course, syllabus.course_id)
    outcomes = db.scalars(
        select(LearningOutcome).where(LearningOutcome.syllabus_id == syllabus.id)
    )
    assessments = db.scalars(select(Assessment).where(Assessment.syllabus_id == syllabus.id))
    return SyllabusDemand(
        course=course.title if course else "",
        outcomes=tuple(row.description or row.code for row in outcomes),
        assessments=tuple((row.name, row.due_week) for row in assessments),
        raw_text=syllabus.raw_text,
    )


def node_candidates(db, demand: SyllabusDemand) -> list[tuple[str, int]]:
    """(node title, pending or verified resources sharing an accepted label).

    The same subject overlap ``match_sources`` (#102) requires of a source.
    """
    by_subject = defaultdict(set)
    for resource_id, subject in db.execute(
        select(ResourceSubject.resource_id, ResourceSubject.subject_id)
        .join(Resource, Resource.id == ResourceSubject.resource_id)
        .where(
            Resource.verification_status.in_(CANDIDATE_STATUSES),
            ResourceSubject.confidence >= 0.6,
        )
    ):
        by_subject[subject].add(resource_id)
    return [
        (title, len(set().union(*(by_subject[s] for s in labels))))
        for title, labels in node_subjects(demand)
    ]
