"""Recommendations and feedback storage (issue #156, epic #154).

Adds tables for recommender system:
- recommendations: recommendations made for a roadmap node to a user
- recommendation_events: user feedback events (shown, opened, helpful, not_helpful, pinned)
- external_results: 7-day cache for external provider queries

Revision ID: 0014_recommendations
Revises: 0013_concept_source_refs
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_recommendations"
down_revision: str | None = "0013_concept_source_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_ref", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("rank", sa.Integer(), server_default="1", nullable=False),
        sa.Column("score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index("ix_recommendations_node_id", "recommendations", ["node_id"])
    op.create_index(
        "ix_recommendations_user_node", "recommendations", ["user_id", "node_id"]
    )

    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('shown', 'opened', 'helpful', 'not_helpful', 'pinned')"
        ),
    )
    op.create_index(
        "ix_recommendation_events_recommendation_id",
        "recommendation_events",
        ["recommendation_id"],
    )

    op.create_table(
        "external_results",
        sa.Column("query_hash", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_external_results_fetched_at", "external_results", ["fetched_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_external_results_fetched_at", table_name="external_results")
    op.drop_table("external_results")
    op.drop_index(
        "ix_recommendation_events_recommendation_id",
        table_name="recommendation_events",
    )
    op.drop_table("recommendation_events")
    op.drop_index("ix_recommendations_user_node", table_name="recommendations")
    op.drop_index("ix_recommendations_node_id", table_name="recommendations")
    op.drop_index("ix_recommendations_user_id", table_name="recommendations")
    op.drop_table("recommendations")
