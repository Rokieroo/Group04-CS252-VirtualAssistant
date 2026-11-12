"""k12_safety: parental consent, safety flag, and minor data protection (issue #164).

Adds parental_consent and parental_consent_at to users table for minors under 18,
and safety_flag to chat_messages to flag sensitive crisis/self-harm interventions.

Revision ID: 0014_k12_safety
Revises: 0013_concept_source_refs
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_k12_safety"
down_revision: str | None = "0014_recommendations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "parental_consent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("parental_consent_at", sa.Text(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "safety_flag",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Not batch mode: rebuilding users on SQLite cascades deletes into courses, roadmaps, and child rows.
    op.drop_column("chat_messages", "safety_flag")
    op.drop_column("users", "parental_consent_at")
    op.drop_column("users", "parental_consent")
