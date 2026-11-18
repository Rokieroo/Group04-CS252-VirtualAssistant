"""recommendations.kind: the three kinds of the unified recommender (issue #155).

Rows written by the #156 placeholder used ``verified`` and ``material``; they mean
``catalog`` and ``user_material``. The check keeps ``verification_status``, which
the API derives from the kind, defined for every stored row.

Revision ID: 0020_recommendation_kinds
Revises: 0019_personal_library
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_recommendation_kinds"
down_revision: str | None = "0019_personal_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMED = {"verified": "catalog", "material": "user_material"}


def upgrade() -> None:
    for old, new in RENAMED.items():
        op.execute(f"UPDATE recommendations SET kind = '{new}' WHERE kind = '{old}'")
    with op.batch_alter_table("recommendations") as batch:
        batch.create_check_constraint(
            "ck_recommendations_kind", "kind IN ('user_material', 'catalog', 'external')"
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_constraint("ck_recommendations_kind", type_="check")
    for old, new in RENAMED.items():
        op.execute(f"UPDATE recommendations SET kind = '{old}' WHERE kind = '{new}'")
