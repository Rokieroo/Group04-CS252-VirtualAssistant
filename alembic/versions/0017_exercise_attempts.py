"""exercise_attempts: a learner's answers to quoted exercises and their marks (issue #115).

Revision ID: 0017_exercise_attempts
Revises: 0016_fsrs_reviews
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_exercise_attempts"
down_revision: str | None = "0016_fsrs_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercise_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.String(36),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_exercise_attempts_user_exercise",
        "exercise_attempts",
        ["user_id", "exercise_id"],
    )
    op.create_index("ix_exercise_attempts_node_id", "exercise_attempts", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_exercise_attempts_node_id", table_name="exercise_attempts")
    op.drop_index("ix_exercise_attempts_user_exercise", table_name="exercise_attempts")
    op.drop_table("exercise_attempts")
