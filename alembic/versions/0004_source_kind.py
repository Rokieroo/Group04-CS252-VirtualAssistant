"""sources.kind: whether a page comes from a syllabus or study material (issue #49).

Kept to this one column so the phase 2 core-loop migration (#63) can chain on it.

Revision ID: 0004_source_kind
Revises: 0003_source_visual_notes
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_source_kind"
down_revision: str | None = "0003_source_visual_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("kind", sa.Text(), nullable=False, server_default="material"),
    )


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("kind")
