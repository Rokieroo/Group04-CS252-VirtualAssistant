"""Verified resource catalog (issue #95, epic #92, ADR 004).

Adds the shared catalog: institutions (authority signal, #96), catalog courses
and their units (#98), a subject taxonomy tagging both resources and roadmap
nodes (#99), and an append-only verification log (#101). ``resources`` gains
the spec 7 columns; existing rows get ``canonical_url = url`` and stay
``pending`` until verified.

``resources`` is extended with plain ``ADD COLUMN`` only, never a batch
rebuild: on SQLite with foreign keys on, dropping the old table would cascade
and delete every ``node_resources`` and ``resource_feedback`` row.

Revision ID: 0008_verified_catalog
Revises: 0007_search_metrics
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_verified_catalog"
down_revision: str | None = "0007_search_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nullable columns added to ``resources``; canonical_url and the status are apart.
_RESOURCE_COLUMNS = (
    ("domain", sa.Text()),
    ("format", sa.Text()),
    ("license", sa.Text()),
    ("is_free", sa.Boolean()),
    ("duration_min", sa.Integer(), sa.CheckConstraint("duration_min >= 0")),
    ("content_hash", sa.String(64)),
    ("source_connector", sa.Text()),
    ("ingested_at", sa.DateTime()),
)


def _tags(table: str, owner: str, target: str) -> None:
    """A subject label on a resource or a roadmap node, with how it was found."""
    op.create_table(
        table,
        sa.Column(
            owner,
            sa.String(36),
            sa.ForeignKey(f"{target}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "subject_id",
            sa.String(36),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1"),
    )
    op.create_index(f"ix_{table}_subject_id", table, ["subject_id"])


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ror_id", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_vi", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("tier", sa.Integer(), server_default="3", nullable=False),
        sa.Column("rank_signal", sa.Text(), nullable=True),
        sa.CheckConstraint("tier BETWEEN 1 AND 3"),
    )

    op.create_table(
        "catalog_courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(36),
            sa.ForeignKey("institutions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.UniqueConstraint("provider", "external_id"),
        sa.CheckConstraint("level IN ('k12', 'undergrad', 'grad')"),
        sa.CheckConstraint("grade BETWEEN 1 AND 12"),
    )
    op.create_index(
        "ix_catalog_courses_institution_id", "catalog_courses", ["institution_id"]
    )

    op.create_table(
        "catalog_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(36),
            sa.ForeignKey("catalog_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        # A unit outlives a removed resource; the course outline stays intact.
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("course_id", "position"),
        sa.CheckConstraint("position >= 1"),
    )
    op.create_index("ix_catalog_units_resource_id", "catalog_units", ["resource_id"])

    op.create_table(
        "subjects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "parent_id", sa.String(36), sa.ForeignKey("subjects.id"), nullable=True
        ),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_vi", sa.Text(), nullable=True),
    )
    _tags("resource_subjects", "resource_id", "resources")
    _tags("node_subjects", "node_id", "roadmap_nodes")

    op.create_table(
        "resource_verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_name", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("checked_by", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_resource_verifications_resource_id_checked_at",
        "resource_verifications",
        ["resource_id", "checked_at"],
    )

    # SQLite cannot ADD COLUMN ... NOT NULL without a default, so backfill first.
    op.add_column(
        "resources",
        sa.Column("canonical_url", sa.Text(), server_default="", nullable=False),
    )
    op.execute("UPDATE resources SET canonical_url = url")
    if op.get_bind().dialect.name != "sqlite":
        # shortcut: SQLite keeps DEFAULT '' (it has no ALTER COLUMN), so one row
        # without a canonical_url could slip in there; the ORM always sets it.
        op.alter_column("resources", "canonical_url", server_default=None)
    op.create_index(
        "ux_resources_canonical_url", "resources", ["canonical_url"], unique=True
    )
    for name, kind, *constraints in _RESOURCE_COLUMNS:
        op.add_column("resources", sa.Column(name, kind, *constraints, nullable=True))
    # Existing rows were never verified: the default makes them pending.
    op.add_column(
        "resources",
        sa.Column(
            "verification_status",
            sa.String(16),
            sa.CheckConstraint(
                "verification_status IN ('pending', 'verified', 'rejected', 'stale')"
            ),
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_resources_verification_status", "resources", ["verification_status"]
    )
    op.create_index("ix_resources_domain", "resources", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_resources_domain", table_name="resources")
    op.drop_index("ix_resources_verification_status", table_name="resources")
    op.drop_index("ux_resources_canonical_url", table_name="resources")
    # Native DROP COLUMN (SQLite >= 3.35): no rebuild, so no cascading deletes.
    for name, *_ in reversed(_RESOURCE_COLUMNS):
        op.drop_column("resources", name)
    op.drop_column("resources", "verification_status")
    op.drop_column("resources", "canonical_url")

    op.drop_index(
        "ix_resource_verifications_resource_id_checked_at",
        table_name="resource_verifications",
    )
    op.drop_table("resource_verifications")
    for table in ("node_subjects", "resource_subjects"):
        op.drop_index(f"ix_{table}_subject_id", table_name=table)
        op.drop_table(table)
    op.drop_table("subjects")
    op.drop_index("ix_catalog_units_resource_id", table_name="catalog_units")
    op.drop_table("catalog_units")
    op.drop_index("ix_catalog_courses_institution_id", table_name="catalog_courses")
    op.drop_table("catalog_courses")
    op.drop_table("institutions")
