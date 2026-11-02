"""Portable SQLAlchemy schema. All timestamps are normalized to UTC.

Alembic (``alembic/versions``) and ``db/schema.sql`` own the DDL; these mappings
must match them, which ``tests/test_schema_sync.py`` enforces.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow():
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must include a UTC offset")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


def _uuid():
    return str(uuid4())


class User(Base):
    """The canonical ``users`` table from migration 0001, extended by 0002."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="student", server_default="student")
    account_level: Mapped[str] = mapped_column(
        Text, default="university", server_default="university"
    )
    birth_year: Mapped[int | None] = mapped_column(Integer)
    companion_mode: Mapped[str] = mapped_column(
        Text, default="buddy", server_default="buddy"
    )
    adult_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    # ISO-8601 UTC text, matching the TEXT column of migration 0001.
    locked_until: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, server_default=func.current_timestamp()
    )
    name: Mapped[str] = mapped_column(String(80), server_default="")
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Ho_Chi_Minh", server_default="Asia/Ho_Chi_Minh"
    )
    personality: Mapped[str] = mapped_column(
        String(16), default="warm", server_default="warm"
    )


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(
        Text, default="university", server_default="university"
    )
    language: Mapped[str] = mapped_column(Text, default="vi", server_default="vi")
    created_at: Mapped[str] = mapped_column(
        Text, server_default=func.current_timestamp()
    )


class Source(Base):
    """One row per PDF page: the unit every citation points to."""

    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        Text, ForeignKey("courses.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # A vision model's notes on what text extraction misses; never cited (issue #9).
    visual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint("page >= 1", name="ck_sources_page"),
        UniqueConstraint("course_id", "file_name", "page"),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Goal(Entity, Base):
    __tablename__ = "goals"
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Team(Entity, Base):
    __tablename__ = "teams"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))


class Membership(Base):
    __tablename__ = "memberships"
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class Invitation(Entity, Base):
    __tablename__ = "invitations"
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(254))
    # The invitee must present the code the owner sent them; email alone is unverified.
    token_hash: Mapped[str] = mapped_column(String(64))
    accepted: Mapped[bool] = mapped_column(default=False)
    team: Mapped[Team] = relationship()
    __table_args__ = (UniqueConstraint("team_id", "email"),)

    @property
    def team_name(self):
        return self.team.name


class Task(Entity, Base):
    __tablename__ = "tasks"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    goal_id: Mapped[str | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL")
    )
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column()
    completed_minutes: Mapped[int] = mapped_column(default=0)
    priority: Mapped[int] = mapped_column(default=2)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(16), default="pending")
    __table_args__ = (
        CheckConstraint("duration_minutes > 0"),
        CheckConstraint(
            "completed_minutes >= 0 AND completed_minutes <= duration_minutes"
        ),
        CheckConstraint("priority BETWEEN 1 AND 3"),
        Index("ix_tasks_assignee_status_due", "assignee_id", "status", "due_at"),
    )


class Availability(Entity, Base):
    __tablename__ = "availability"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    __table_args__ = (CheckConstraint("ends_at > starts_at"),)


class BusyBlock(Entity, Base):
    __tablename__ = "busy_blocks"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    title: Mapped[str] = mapped_column(String(200), default="Busy")
    __table_args__ = (CheckConstraint("ends_at > starts_at"),)


class ScheduleEntry(Entity, Base):
    __tablename__ = "schedule_entries"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(16), default="planned")
    actual_minutes: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        CheckConstraint("ends_at > starts_at"),
        Index("ix_schedule_user_status_start", "user_id", "status", "starts_at"),
    )


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_entries.id", ondelete="CASCADE"), unique=True
    )
    message: Mapped[str] = mapped_column(String(500))
    read: Mapped[bool] = mapped_column(default=False)


class ChatMessage(Entity, Base):
    __tablename__ = "chat_messages"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
