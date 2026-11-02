"""Preserve exact source provenance when PDFs share page numbers.

Revision ID: 0002_concept_source_ids
Revises: 0001_initial
"""
import sqlalchemy as sa

from alembic import op

revision = "0002_concept_source_ids"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("concepts", sa.Column("source_ids", sa.Text(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("concepts", "source_ids")
