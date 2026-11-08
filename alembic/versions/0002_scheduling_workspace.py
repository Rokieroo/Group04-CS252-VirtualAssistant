"""Scheduling workspace and companion tables on the canonical users table.

Revision ID: 0002_scheduling_workspace
Revises: 0001_initial
Create Date: 2026-10-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_scheduling_workspace"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ]


def _user_fk(ondelete: str | None = "CASCADE") -> sa.Column:
    return sa.Column(
        "user_id",
        sa.Text(),
        sa.ForeignKey("users.id", ondelete=ondelete),
        nullable=False,
    )


def upgrade() -> None:
    # Plain ALTERs: a batch "recreate" of users would cascade-delete courses on SQLite.
    op.add_column(
        "users", sa.Column("name", sa.String(80), server_default="", nullable=False)
    )
    op.add_column(
        "users",
        sa.Column(
            "timezone", sa.String(64), server_default="Asia/Ho_Chi_Minh", nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column("personality", sa.String(16), server_default="warm", nullable=False),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        _user_fk(),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "goals",
        *_entity(),
        sa.Column(
            "owner_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_goals_owner_id", "goals", ["owner_id"])

    op.create_table(
        "teams",
        *_entity(),
        sa.Column("owner_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_index("ix_teams_owner_id", "teams", ["owner_id"])

    op.create_table(
        "memberships",
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "invitations",
        *_entity(),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("team_id", "email"),
    )
    op.create_index("ix_invitations_team_id", "invitations", ["team_id"])

    op.create_table(
        "tasks",
        *_entity(),
        sa.Column("owner_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "assignee_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "goal_id",
            sa.String(36),
            sa.ForeignKey("goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("completed_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("duration_minutes > 0"),
        sa.CheckConstraint(
            "completed_minutes >= 0 AND completed_minutes <= duration_minutes"
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 3"),
    )
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"])
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])
    op.create_index("ix_tasks_team_id", "tasks", ["team_id"])
    op.create_index(
        "ix_tasks_assignee_status_due", "tasks", ["assignee_id", "status", "due_at"]
    )

    for table, extra in (
        ("availability", []),
        ("busy_blocks", [sa.Column("title", sa.String(200), nullable=False)]),
    ):
        op.create_table(
            table,
            *_entity(),
            _user_fk(),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            *extra,
            sa.CheckConstraint("ends_at > starts_at"),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    op.create_table(
        "schedule_entries",
        *_entity(),
        _user_fk(ondelete=None),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at"),
    )
    op.create_index("ix_schedule_entries_user_id", "schedule_entries", ["user_id"])
    op.create_index("ix_schedule_entries_task_id", "schedule_entries", ["task_id"])
    op.create_index(
        "ix_schedule_user_status_start",
        "schedule_entries",
        ["user_id", "status", "starts_at"],
    )

    op.create_table(
        "notifications",
        *_entity(),
        _user_fk(),
        sa.Column(
            "entry_id",
            sa.String(36),
            sa.ForeignKey("schedule_entries.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("entry_id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "chat_messages",
        *_entity(),
        _user_fk(),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])


def downgrade() -> None:
    # Tables first (indexes go with them), in reverse foreign-key order.
    for table in (
        "chat_messages",
        "notifications",
        "schedule_entries",
        "busy_blocks",
        "availability",
        "tasks",
        "invitations",
        "memberships",
        "teams",
        "goals",
        "auth_sessions",
    ):
        op.drop_table(table)
    for column in ("personality", "timezone", "name"):
        op.execute(f"ALTER TABLE users DROP COLUMN {column}")  # SQLite >= 3.35
