"""placement: concepts a learner already knows and their placement tests (issue #166).

Revision ID: 0018_placement
Revises: 0017_exercise_attempts
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_placement"
down_revision: str | None = "0017_exercise_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("roadmap_nodes", sa.Column("known", sa.Text(), nullable=True))
    op.create_table(
        "placements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "roadmap_id",
            sa.String(36),
            sa.ForeignKey("roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("skipped", sa.Text(), nullable=False),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "exercise_id",
            sa.String(36),
            sa.ForeignKey("exercises.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_placements_user_roadmap", "placements", ["user_id", "roadmap_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_placements_user_roadmap", table_name="placements")
    op.drop_table("placements")
    # Not batch mode: rebuilding roadmap_nodes on SQLite cascades deletes into tasks.
    op.drop_column("roadmap_nodes", "known")
