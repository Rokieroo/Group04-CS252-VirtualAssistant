"""Subject tagging of nodes and resources (issue #99).

Labels live in ``resource_subjects`` / ``node_subjects`` (0008). This adds the
vectors the tagger computes, kept for hybrid retrieval, and ``resources.tagged_at``
so the daily sweep tags each resource once instead of every day. A node's vector
sits on the node row, so deleting the roadmap deletes it with the learner's data.

Plain ADD COLUMN only (see 0008): no table rebuild, so no cascading deletes on SQLite.

Revision ID: 0009_subject_tagging
Revises: 0008_verified_catalog
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_subject_tagging"
down_revision: str | None = "0008_verified_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VECTORS = ("embedding", "embedding_model")  # JSON float list, and the model that made it


def upgrade() -> None:
    for table in ("resources", "roadmap_nodes"):
        for column in _VECTORS:
            op.add_column(table, sa.Column(column, sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("tagged_at", sa.DateTime(), nullable=True))
    # The sweep looks for untagged resources.
    op.create_index("ix_resources_tagged_at", "resources", ["tagged_at"])


def downgrade() -> None:
    op.drop_index("ix_resources_tagged_at", table_name="resources")
    op.drop_column("resources", "tagged_at")
    for table in ("roadmap_nodes", "resources"):
        for column in reversed(_VECTORS):
            op.drop_column(table, column)
