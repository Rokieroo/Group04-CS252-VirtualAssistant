"""node_materials.method: who decided a page belongs to a node (issue #114).

"auto" rows come from the material mapper and are recomputed on every run;
"manual" rows are the learner's own decision (attach, confirm, or reject with
confidence 0) and are never overwritten. Rows before this revision were all
attached by hand.

Revision ID: 0011_material_method
Revises: 0010_quoted_exercises
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_material_method"
down_revision: str | None = "0010_quoted_exercises"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "node_materials",
        sa.Column("method", sa.Text(), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    with op.batch_alter_table("node_materials") as batch:
        batch.drop_column("method")
