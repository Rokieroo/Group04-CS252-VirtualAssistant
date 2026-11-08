"""Visual notes per PDF page, written by a vision model at upload (issue #9).

Kept apart from sources.text so citations always point at the slide's own text.

Revision ID: 0003_source_visual_notes
Revises: 0002_scheduling_workspace
Create Date: 2026-10-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_source_visual_notes"
down_revision: str | None = "0002_scheduling_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("visual_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("visual_notes")
