"""Shared-catalog snapshots (#105): copy the catalog to a new machine or to CI.

Only shared rows travel: the resources catalog connectors stored, their
courses, units, institutions, labels, vectors and verification history. Nothing
a learner owns (courses, roadmaps, uploads, web-search results) is read, and
subjects are seeded from ``data/catalog/subjects.yaml`` rather than copied.

Loading is idempotent and merges by natural key, so a snapshot loads onto a
database that already holds part of the catalog: a row whose key exists keeps
its local id and local state, and the rows pointing at it are rewritten to it.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, select
from sqlalchemy.orm import Session

from app.catalog import verification as rules
from app.catalog.taxonomy import ensure_taxonomy

from .catalog_models import CatalogEmbedding
from .models import (
    CatalogCourse,
    CatalogUnit,
    Institution,
    Resource,
    ResourceSubject,
    ResourceVerification,
    Subject,
)

FORMAT = 1
SAMPLE = Path(__file__).resolve().parents[3] / "data/catalog/snapshots/csc10014-sample.json"


@dataclass(frozen=True)
class _Table:
    model: type
    key: tuple[str, ...]  # natural key: a row with the same values is the same row
    refs: dict[str, type] = field(default_factory=dict)  # column -> model it points at


# In load order: every table comes after the tables it points at.
TABLES = (
    _Table(Institution, ("ror_id",)),
    _Table(CatalogCourse, ("provider", "external_id"), {"institution_id": Institution}),
    _Table(Resource, ("canonical_url",), {"catalog_course_id": CatalogCourse}),
    _Table(
        CatalogUnit, ("course_id", "position"),
        {"course_id": CatalogCourse, "resource_id": Resource},
    ),
    _Table(
        ResourceSubject, ("resource_id", "subject_id"),
        {"resource_id": Resource, "subject_id": Subject},
    ),
    _Table(ResourceVerification, ("id",), {"resource_id": Resource}),
    _Table(CatalogEmbedding, ("id", "kind"), {"id": Resource, "resource_id": Resource}),
)


def _rows(db: Session) -> dict[type, list]:
    """The shared rows, each table restricted to what the exported resources need."""
    resources = list(
        db.scalars(
            select(Resource)
            .where(Resource.source_connector.is_not(None))  # never web-search rows
            .order_by(Resource.canonical_url)
        )
    )
    ids = [r.id for r in resources]
    courses = list(
        db.scalars(select(CatalogCourse).order_by(CatalogCourse.provider, CatalogCourse.external_id))
    )
    owners = {c.institution_id for c in courses if c.institution_id}
    return {
        Institution: list(
            db.scalars(
                select(Institution).where(Institution.id.in_(owners)).order_by(Institution.ror_id)
            )
        ),
        CatalogCourse: courses,
        Resource: resources,
        CatalogUnit: list(
            db.scalars(select(CatalogUnit).order_by(CatalogUnit.course_id, CatalogUnit.position))
        ),
        ResourceSubject: list(
            db.scalars(
                select(ResourceSubject)
                .where(ResourceSubject.resource_id.in_(ids))
                .order_by(ResourceSubject.resource_id, ResourceSubject.subject_id)
            )
        ),
        ResourceVerification: list(
            db.scalars(
                select(ResourceVerification)
                .where(ResourceVerification.resource_id.in_(ids))
                .order_by(ResourceVerification.checked_at, ResourceVerification.id)
            )
        ),
        CatalogEmbedding: list(
            db.scalars(
                select(CatalogEmbedding)
                .where(CatalogEmbedding.kind == "resource", CatalogEmbedding.id.in_(ids))
                .order_by(CatalogEmbedding.id)
            )
        ),
    }


def _is_time(column) -> bool:
    return isinstance(getattr(column.type, "impl", column.type), DateTime)


def export_snapshot(db: Session, now: datetime) -> dict:
    """The shared catalog as JSON-ready data, in a stable order for readable diffs."""
    tables = {}
    for table in TABLES:
        columns = table.model.__table__.columns
        tables[table.model.__tablename__] = [
            {
                c.key: value.isoformat() if _is_time(c) and value else value
                for c in columns
                for value in [getattr(row, c.key)]
            }
            for row in _rows(db)[table.model]
        ]
    return {"format": FORMAT, "exported_at": now.isoformat(), "tables": tables}


def _decode(model: type, row: dict) -> dict:
    columns = {c.key: c for c in model.__table__.columns}
    return {
        key: datetime.fromisoformat(value) if _is_time(columns[key]) and value else value
        for key, value in row.items()
        if key in columns  # a column dropped since the export is ignored
    }


def _existing(db: Session, table: _Table, values: dict):
    model = table.model
    return db.scalar(select(model).where(*(getattr(model, k) == values[k] for k in table.key)))


def load_snapshot(db: Session, snapshot: dict, now: datetime, *, restamp_by: str | None = None) -> Counter:
    """Merge ``snapshot`` into the catalog; return the rows added per table.

    ``restamp_by`` is for the bundled dev/CI sample only: every verified resource
    this load adds gets four fresh passes by that name, so a sample older than
    ``FRESH_FOR`` still shows on a new machine. Production loads a real snapshot
    without it and lets ``verify_catalog`` re-check what has gone stale.
    """
    if snapshot.get("format") != FORMAT:
        raise ValueError(f"unsupported snapshot format {snapshot.get('format')!r}")
    ensure_taxonomy(db)
    local = {table.model: {} for table in TABLES}  # snapshot id -> local id
    local[Subject] = {s: s for s in db.scalars(select(Subject.id))}
    added, verified = Counter(), []
    for table in TABLES:
        name, model = table.model.__tablename__, table.model
        for row in snapshot["tables"].get(name, []):
            values = _decode(model, row)
            if not _point_locally(table, values, local):
                continue
            existing = _existing(db, table, values)
            if existing is None:
                db.add(model(**values))
                added[name] += 1
                if model is Resource and values.get("verification_status") == "verified":
                    verified.append(values["id"])
            if "id" in row and "id" not in table.refs:
                local[model][row["id"]] = existing.id if existing is not None else values["id"]
        db.flush()
    if restamp_by and verified:
        for resource_id in verified:
            for check in rules.CHECKS:
                db.add(
                    ResourceVerification(
                        resource_id=resource_id,
                        check_name=check,
                        result=rules.PASS,
                        details=json.dumps({"reason": "sample snapshot"}),
                        checked_at=now,
                        checked_by=restamp_by,
                    )
                )
        added["restamped"] = len(verified)
    db.flush()
    return added


def _point_locally(table: _Table, values: dict, local: dict) -> bool:
    """Rewrite references to local ids; False when a required one is missing here."""
    for column, target in table.refs.items():
        if values.get(column) is None:
            continue
        mapped = local[target].get(values[column])
        if mapped is None and not table.model.__table__.columns[column].nullable:
            return False
        values[column] = mapped
    return True


def read_snapshot(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_snapshot(path: Path, snapshot: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
