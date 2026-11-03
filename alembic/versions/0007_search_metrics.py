"""Cost and latency of resource searches, for the cost dashboard (issue #69).

``resource_searches`` holds one row per node search (queries, candidates, kept
resources, LLM and search spend); each ``search_runs`` row, one provider call,
now records its latency and cost and points at its search.

Revision ID: 0007_search_metrics
Revises: 0006_jobs_and_link_checks
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_search_metrics"
down_revision: str | None = "0006_jobs_and_link_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resource_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        # Spend stays on the books when a roadmap is deleted.
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("node_title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("cache_hit", sa.Integer(), server_default="0", nullable=False),
        sa.Column("queries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidates", sa.Integer(), server_default="0", nullable=False),
        sa.Column("vetted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("kept", sa.Integer(), server_default="0", nullable=False),
        sa.Column("llm_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("llm_cost_usd", sa.Float(), server_default="0", nullable=False),
        sa.Column("search_cost_usd", sa.Float(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    op.create_index("ix_resource_searches_node_id", "resource_searches", ["node_id"])
    op.create_index("ix_resource_searches_user_id", "resource_searches", ["user_id"])
    # The dashboard reads a time window.
    op.create_index("ix_resource_searches_created_at", "resource_searches", ["created_at"])

    # Batch mode: SQLite cannot add a foreign key with ALTER TABLE.
    with op.batch_alter_table("search_runs") as batch:
        batch.add_column(
            sa.Column(
                "search_id",
                sa.String(36),
                sa.ForeignKey(
                    "resource_searches.id",
                    name="fk_search_runs_search_id",
                    ondelete="CASCADE",
                ),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False)
        )
        batch.add_column(
            sa.Column("cost_usd", sa.Float(), server_default="0", nullable=False)
        )
    op.create_index("ix_search_runs_search_id", "search_runs", ["search_id"])
    op.create_index("ix_search_runs_created_at", "search_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_search_runs_created_at", table_name="search_runs")
    op.drop_index("ix_search_runs_search_id", table_name="search_runs")
    with op.batch_alter_table("search_runs") as batch:
        batch.drop_constraint("fk_search_runs_search_id", type_="foreignkey")
        batch.drop_column("cost_usd")
        batch.drop_column("latency_ms")
        batch.drop_column("search_id")
    op.drop_index("ix_resource_searches_created_at", table_name="resource_searches")
    op.drop_index("ix_resource_searches_user_id", table_name="resource_searches")
    op.drop_index("ix_resource_searches_node_id", table_name="resource_searches")
    op.drop_table("resource_searches")
