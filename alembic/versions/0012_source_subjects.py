"""source_subjects: the subjects each page of a learner's material teaches (issue #102).

A node's catalog sources skip the subjects its private material already covers.
Tagging a page is costly, so it happens when the page is mapped or attached, never
while reading sources. Pages from before this revision get their tags on the next
mapping run; until then they cover nothing and hide no catalog source.

Revision ID: 0012_source_subjects
Revises: 0011_material_method
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_source_subjects"
down_revision: str | None = "0011_material_method"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_subjects",
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Text(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("confidence", sa.Double(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_subjects")
