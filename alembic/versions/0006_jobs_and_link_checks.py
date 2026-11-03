"""Background jobs, the shared search cache and link maintenance (issue #68).

Adds the jobs queue the worker polls, the 7-day search cache keyed by node
signature (spec 11.8) and the columns the daily link check needs (spec 11.7).

Revision ID: 0006_jobs_and_link_checks
Revises: 0005_core_loop
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_jobs_and_link_checks"
down_revision: str | None = "0005_core_loop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),
    )
    # The worker scans queued jobs by run_after; the cron dedupes on dedupe_key.
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"])
    op.create_index("ux_jobs_dedupe_key", "jobs", ["dedupe_key"], unique=True)
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])

    op.create_table(
        "search_cache",
        sa.Column("signature", sa.String(64), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_search_cache_expires_at", "search_cache", ["expires_at"])

    op.add_column(
        "resources", sa.Column("last_checked_at", sa.DateTime(), nullable=True)
    )
    op.add_column("resources", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column(
        "resources",
        sa.Column("failed_checks", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "node_resources",
        sa.Column("status", sa.Text(), server_default="shown", nullable=False),
    )


def downgrade() -> None:
    with op.batch_alter_table("node_resources") as batch:
        batch.drop_column("status")
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("failed_checks")
        batch.drop_column("http_status")
        batch.drop_column("last_checked_at")
    op.drop_index("ix_search_cache_expires_at", table_name="search_cache")
    op.drop_table("search_cache")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_index("ux_jobs_dedupe_key", table_name="jobs")
    op.drop_index("ix_jobs_status_run_after", table_name="jobs")
    op.drop_table("jobs")
