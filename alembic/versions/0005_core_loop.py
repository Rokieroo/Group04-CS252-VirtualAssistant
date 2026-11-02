"""Core syllabus -> roadmap -> schedule loop (issue #63).

Adds the Phase 2 tables and tasks.roadmap_node_id, which connects the loop to
the existing tasks table (sources.kind came first, in 0004_source_kind). The
DDL is portable: SQLite for local tests and PostgreSQL for staging/production.

Revision ID: 0005_core_loop
Revises: 0004_source_kind
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_core_loop"
down_revision: str | None = "0004_source_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "syllabi",
        _id(),
        sa.Column(
            "course_id",
            sa.Text(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "learning_outcomes",
        _id(),
        sa.Column(
            "syllabus_id",
            sa.String(36),
            sa.ForeignKey("syllabi.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "bloom_level",
            sa.Text(),
            server_default="understand",
            nullable=False,
        ),
    )

    op.create_table(
        "assessments",
        _id(),
        sa.Column(
            "syllabus_id",
            sa.String(36),
            sa.ForeignKey("syllabi.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="0", nullable=False),
        sa.Column("due_week", sa.Integer(), nullable=True),
    )

    op.create_table(
        "roadmaps",
        _id(),
        sa.Column(
            "course_id",
            sa.Text(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "roadmap_nodes",
        _id(),
        sa.Column(
            "roadmap_id",
            sa.String(36),
            sa.ForeignKey("roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("covers", sa.Text(), nullable=True),
    )

    op.create_table(
        "resources",
        _id(),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), server_default="web", nullable=False),
        sa.Column("kind", sa.Text(), server_default="article", nullable=False),
        sa.Column("lang", sa.Text(), server_default="vi", nullable=False),
    )

    op.create_table(
        "node_resources",
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "relevance_score", sa.Float(), server_default="0", nullable=False
        ),
    )

    op.create_table(
        "resource_feedback",
        _id(),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
    )

    op.create_table(
        "search_runs",
        _id(),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), server_default="web", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "results_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # Foreign keys are not indexed automatically; every lookup below is by one of them.
    op.create_index("ix_syllabi_course_id", "syllabi", ["course_id"])
    op.create_index("ix_learning_outcomes_syllabus_id", "learning_outcomes", ["syllabus_id"])
    op.create_index("ix_assessments_syllabus_id", "assessments", ["syllabus_id"])
    op.create_index("ix_roadmaps_course_id", "roadmaps", ["course_id"])
    op.create_index("ix_roadmaps_user_id", "roadmaps", ["user_id"])
    op.create_index("ix_roadmap_nodes_roadmap_id", "roadmap_nodes", ["roadmap_id"])
    op.create_index("ix_node_resources_resource_id", "node_resources", ["resource_id"])
    op.create_index("ix_resource_feedback_user_id", "resource_feedback", ["user_id"])
    op.create_index("ix_resource_feedback_resource_id", "resource_feedback", ["resource_id"])
    op.create_index("ix_search_runs_user_id", "search_runs", ["user_id"])

    # SQLite's op.add_column cannot attach a foreign key, so recreate tasks in
    # batch mode. Pass the existing unnamed CHECK constraints explicitly so the
    # recreate does not silently drop them.
    with op.batch_alter_table(
        "tasks",
        table_args=(
            sa.CheckConstraint("duration_minutes > 0"),
            sa.CheckConstraint(
                "completed_minutes >= 0 AND completed_minutes <= duration_minutes"
            ),
            sa.CheckConstraint("priority BETWEEN 1 AND 3"),
        ),
    ) as batch:
        batch.add_column(sa.Column("roadmap_node_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_tasks_roadmap_node_id",
            "roadmap_nodes",
            ["roadmap_node_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_tasks_roadmap_node_id", ["roadmap_node_id"])


def downgrade() -> None:
    with op.batch_alter_table(
        "tasks",
        table_args=(
            sa.CheckConstraint("duration_minutes > 0"),
            sa.CheckConstraint(
                "completed_minutes >= 0 AND completed_minutes <= duration_minutes"
            ),
            sa.CheckConstraint("priority BETWEEN 1 AND 3"),
        ),
    ) as batch:
        batch.drop_index("ix_tasks_roadmap_node_id")
        batch.drop_column("roadmap_node_id")

    # Reverse foreign-key order.
    for table in (
        "search_runs",
        "resource_feedback",
        "node_resources",
        "resources",
        "roadmap_nodes",
        "roadmaps",
        "assessments",
        "learning_outcomes",
        "syllabi",
    ):
        op.drop_table(table)
