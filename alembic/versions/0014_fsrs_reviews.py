"""fsrs_reviews: review cards, review logs, and FSRS spaced repetition (issue #162).

Revision ID: 0014_fsrs_reviews
Revises: 0013_concept_source_refs
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_fsrs_reviews"
down_revision: str | None = "0013_concept_source_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_cards",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            sa.Text(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column(
            "stability", sa.Float(), server_default=sa.text("0.0"), nullable=False
        ),
        sa.Column(
            "difficulty", sa.Float(), server_default=sa.text("0.0"), nullable=False
        ),
        sa.Column("state", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("step", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_review", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_review_cards_due_at", "review_cards", ["due_at"])
    op.create_index("ix_review_cards_node_id", "review_cards", ["node_id"])

    op.create_table(
        "review_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Text(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "elapsed_days", sa.Float(), server_default=sa.text("0.0"), nullable=False
        ),
        sa.Column(
            "scheduled_days", sa.Float(), server_default=sa.text("0.0"), nullable=False
        ),
        sa.Column("stability", sa.Float(), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
    )
    op.create_index("ix_review_logs_user_item", "review_logs", ["user_id", "item_id"])
    op.create_index("ix_review_logs_node_id", "review_logs", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_review_logs_node_id", table_name="review_logs")
    op.drop_index("ix_review_logs_user_item", table_name="review_logs")
    op.drop_table("review_logs")
    op.drop_index("ix_review_cards_node_id", table_name="review_cards")
    op.drop_index("ix_review_cards_due_at", table_name="review_cards")
    op.drop_table("review_cards")
