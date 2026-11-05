"""Portable SQLAlchemy schema. All timestamps are normalized to UTC.

Alembic (``alembic/versions``) and ``db/schema.sql`` own the DDL; these mappings
must match them, which ``tests/test_schema_sync.py`` enforces.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)
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
    """One row per document page (PDF, DOCX or text): the unit every citation points to."""

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
    kind: Mapped[str] = mapped_column(
        Text, default="material", server_default="material"
    )  # syllabus | material
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
    roadmap_node_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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


class Syllabus(Base):
    __tablename__ = "syllabi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.current_timestamp()
    )

    @property
    def syllabus_id(self) -> str:
        return self.id


class LearningOutcome(Base):
    __tablename__ = "learning_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    syllabus_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("syllabi.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    bloom_level: Mapped[str] = mapped_column(
        Text, default="understand", server_default="understand"
    )


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    syllabus_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("syllabi.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    due_week: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Roadmap(Base):
    __tablename__ = "roadmaps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.current_timestamp()
    )

    @property
    def roadmap_id(self) -> str:
        return self.id


class RoadmapNode(Base):
    __tablename__ = "roadmap_nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    roadmap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmaps.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    covers: Mapped[str | None] = mapped_column(Text, nullable=True)
    concept_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("concepts.id", ondelete="SET NULL")
    )

    @property
    def kind(self) -> str:
        return self.type


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text, default="web", server_default="web")
    kind: Mapped[str] = mapped_column(Text, default="article", server_default="article")
    lang: Mapped[str] = mapped_column(Text, default="vi", server_default="vi")
    # Link maintenance (spec 11.7): the daily check updates these three.
    last_checked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_checks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    catalog_course_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_courses.id", ondelete="SET NULL")
    )
    # Verified catalog (migration 0008). One row per canonical_url; url is what the user opens.
    canonical_url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_free: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_min: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("duration_min >= 0"), nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_connector: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint(
            "verification_status IN ('pending', 'verified', 'rejected', 'stale')"
        ),
        default="pending",
        server_default="pending",
        index=True,
    )
    __table_args__ = (
        Index("ux_resources_canonical_url", "canonical_url", unique=True),
        Index("ix_resources_domain", "domain"),
    )


class NodeResource(Base):
    __tablename__ = "node_resources"
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    resource_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    relevance_score: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0"
    )
    status: Mapped[str] = mapped_column(  # shown | replaced | removed (spec 7.1)
        Text, default="shown", server_default="shown"
    )


class ResourceFeedback(Base):
    __tablename__ = "resource_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResourceSearch(Base):
    """One resource search of a node: what it found and spent (issue #69)."""

    __tablename__ = "resource_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    node_title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # ready | insufficient
    cache_hit: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    queries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    vetted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    kept: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    search_cost_usd: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0"
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=func.current_timestamp(),
        index=True,
    )


class SearchRun(Base):
    """One provider call; ``search_id`` groups the calls of one resource search."""

    __tablename__ = "search_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text, default="web", server_default="web")
    status: Mapped[str] = mapped_column(
        Text, default="pending", server_default="pending"
    )
    results_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=func.current_timestamp(),
        index=True,
    )
    search_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "resource_searches.id", name="fk_search_runs_search_id", ondelete="CASCADE"
        ),
        index=True,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")


class Job(Base):
    """A unit of background work (see jobs.py). ``payload`` and ``result`` are JSON."""

    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),
        Index("ix_jobs_status_run_after", "status", "run_after"),
        Index("ux_jobs_dedupe_key", "dedupe_key", unique=True),
    )


class SearchCacheEntry(Base):
    """Search results shared by every user studying the same node (spec 11.8)."""

    __tablename__ = "search_cache"
    signature: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


# --- verified catalog (migration 0008, ADR 004) ---------------------------------


class Institution(Base):
    """A university or official K-12 source; ``tier`` is its ``DomainTier`` (#96)."""

    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ror_id: Mapped[str] = mapped_column(Text, unique=True)  # or vn-k12:<slug>
    name: Mapped[str] = mapped_column(Text)
    name_vi: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    rank_signal: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    __table_args__ = (CheckConstraint("tier BETWEEN 1 AND 3"),)


class CatalogCourse(Base):
    """A course or book of a provider; upserts key on ``(provider, external_id)``."""

    __tablename__ = "catalog_courses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text)  # k12 | undergrad | grad
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint("provider", "external_id"),
        CheckConstraint("level IN ('k12', 'undergrad', 'grad')"),
        CheckConstraint("grade BETWEEN 1 AND 12"),
    )


class CatalogUnit(Base):
    """A lecture, chapter or problem set; one resource may serve many courses."""

    __tablename__ = "catalog_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_courses.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="SET NULL"), index=True
    )
    __table_args__ = (
        UniqueConstraint("course_id", "position"),
        CheckConstraint("position >= 1"),
    )


class Subject(Base):
    """A node of the subject taxonomy: field -> subject -> topic (#99)."""

    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("subjects.id"))
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    name_vi: Mapped[str | None] = mapped_column(Text, nullable=True)


class _Tag:
    """How a subject label was assigned: ``method`` is rule | embedding | llm | manual."""

    subject_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    method: Mapped[str] = mapped_column(Text)

    @declared_attr.directive
    def __table_args__(cls):  # a constraint belongs to one table, so one per subclass
        return (CheckConstraint("confidence >= 0 AND confidence <= 1"),)


class ResourceSubject(_Tag, Base):
    __tablename__ = "resource_subjects"
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )


class NodeSubject(_Tag, Base):
    """Deleted with its roadmap; the shared resources and subjects stay."""

    __tablename__ = "node_subjects"
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )


class ResourceVerification(Base):
    """Append-only: one row per check on a resource (#101). Insert, never update."""

    __tablename__ = "resource_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE")
    )
    check_name: Mapped[str] = mapped_column(Text)  # fetch | domain | license | metadata
    result: Mapped[str] = mapped_column(Text)  # pass | fail | review
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    checked_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.current_timestamp()
    )
    checked_by: Mapped[str] = mapped_column(Text)  # job name or admin user id
    __table_args__ = (
        Index(
            "ix_resource_verifications_resource_id_checked_at",
            "resource_id",
            "checked_at",
        ),
    )


# Register graph/exercise extensions on the canonical schema metadata.
from . import catalog_models  # noqa: F401
