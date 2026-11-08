"""concept_source_refs: which file each cited page belongs to (PR #70).

``source_pages`` holds bare page numbers, so two decks of one course share them: a
concept from page 3 of week01.pdf also matched page 3 of week02.pdf. ``source_refs``
is a JSON list of {"file_name", "page"}; it names pages, not source rows, because a
re-upload replaces a file's rows under new ids. Concepts saved before this revision
keep "[]" and fall back to page numbers until the next proposal revises them.

Revision ID: 0013_concept_source_refs
Revises: 0012_source_subjects
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_concept_source_refs"
down_revision: str | None = "0012_source_subjects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "concepts",
        sa.Column("source_refs", sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    # Not batch mode: rebuilding concepts on SQLite cascades deletes into cards and items.
    op.drop_column("concepts", "source_refs")
