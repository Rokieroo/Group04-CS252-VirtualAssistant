"""Personal learning library and guide preferences."""

import sqlalchemy as sa

from alembic import op

revision = "0017_personal_library"
down_revision = "0016_fsrs_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "personal_sources",
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_key", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
    )
    for name in ("guide_enabled", "weekly_reminder"):
        op.add_column(
            "users", sa.Column(name, sa.Integer(), nullable=False, server_default="1")
        )


def downgrade():
    op.drop_column("users", "weekly_reminder")
    op.drop_column("users", "guide_enabled")
    op.drop_table("personal_sources")
