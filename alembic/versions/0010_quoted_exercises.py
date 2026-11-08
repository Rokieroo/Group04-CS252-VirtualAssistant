"""Frozen schema declarations; dialect-aware DDL independent of future ORM changes."""

import sqlalchemy as sa

from alembic import op

revision = "0010_quoted_exercises"
down_revision = "0009_roadmap_graph"
branch_labels = None
depends_on = None


def _create_tables():
    op.create_table(
        "exercises",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("quote_hash", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column(
            "owner_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("choices", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("solution_ref", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("bloom_level", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "prompt IS NOT NULL OR location IS NOT NULL", name="ck_exercise_content"
        ),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_exercise_difficulty"),
        sa.CheckConstraint(
            "origin IN ('catalog','user_material')", name="ck_exercise_origin"
        ),
        sa.CheckConstraint(
            "(origin = 'catalog' AND resource_id IS NOT NULL AND source_id IS NULL AND owner_id IS NULL) OR (origin = 'user_material' AND source_id IS NOT NULL AND resource_id IS NULL AND owner_id IS NOT NULL AND page IS NOT NULL AND page >= 1)",
            name="ck_exercise_source",
        ),
        sa.CheckConstraint(
            "type IN ('mcq','numeric','short','proof','code')", name="ck_exercise_type"
        ),
    )
    op.create_table(
        "exercise_subjects",
        sa.Column(
            "exercise_id",
            sa.String(36),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Text(),
            sa.ForeignKey("subjects.id"),
            primary_key=True,
            nullable=False,
        ),
    )
    op.create_table(
        "node_exercises",
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.String(36),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("role", sa.Text(), primary_key=True, nullable=False),
        sa.CheckConstraint(
            "role IN ('practice','checkpoint')", name="ck_node_exercise_role"
        ),
    )


INDEXES = ["CREATE INDEX ix_exercises_owner_id ON exercises (owner_id)"]


def upgrade():
    _create_tables()
    for ddl in INDEXES:
        op.execute(ddl)
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE items ADD COLUMN exercise_id VARCHAR(36) REFERENCES exercises(id) ON DELETE CASCADE"
        )
    else:
        op.add_column(
            "items",
            sa.Column(
                "exercise_id",
                sa.String(36),
                sa.ForeignKey(
                    "exercises.id", name="fk_items_exercise_id", ondelete="CASCADE"
                ),
            ),
        )
    op.execute("UPDATE items SET status = 'rejected' WHERE exercise_id IS NULL")


def downgrade():
    op.drop_column("items", "exercise_id")
    op.drop_table("node_exercises")
    op.drop_table("exercise_subjects")
    op.drop_table("exercises")
