"""Catalog, private graph and quoted-exercise persistence (#96, #99, #100, #102, #115)."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, UTCDateTime, _uuid, utcnow


class Concept(Base):
    __tablename__ = "concepts"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        Text, ForeignKey("courses.id", ondelete="CASCADE")
    )
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    bloom_level: Mapped[str] = mapped_column(
        Text, default="understand", server_default="understand"
    )
    source_pages: Mapped[str | None] = mapped_column(Text)
    confirmed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    __table_args__ = (UniqueConstraint("course_id", "slug"),)


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ror_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    name_vi: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text, index=True)
    tier: Mapped[int] = mapped_column(Integer)
    rank_signal: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    __table_args__ = (
        CheckConstraint("tier BETWEEN 1 AND 3", name="ck_institutions_tier"),
    )


class CatalogCourse(Base):
    __tablename__ = "catalog_courses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    institution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(
        Text, default="undergrad", server_default="undergrad"
    )
    grade: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(Text, default="en", server_default="en")
    license: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("provider", "external_id"),)


class CatalogUnit(Base):
    __tablename__ = "catalog_units"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_courses.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE")
    )


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(Text, ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(Text)
    name_vi: Mapped[str] = mapped_column(Text)


class ResourceSubject(Base):
    __tablename__ = "resource_subjects"
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column()
    method: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_resource_subject_confidence"
        ),
    )


class NodeSubject(Base):
    __tablename__ = "node_subjects"
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column()
    method: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_node_subject_confidence"
        ),
    )


class CatalogEmbedding(Base):
    __tablename__ = "catalog_embeddings"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    vector: Mapped[str] = mapped_column(Text)
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE")
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE")
    )


class NodeSourceStatus(Base):
    __tablename__ = "node_source_status"
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ResourceVerification(Base):
    __tablename__ = "resource_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE"), index=True
    )
    check: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    checked_by: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL")
    )


class RoadmapEdge(Base):
    __tablename__ = "roadmap_edges"
    roadmap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmaps.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column()
    reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    created_by: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (
        CheckConstraint("parent_id <> child_id", name="ck_roadmap_edge_self"),
        CheckConstraint("kind IN ('soft','strict')", name="ck_roadmap_edge_kind"),
        CheckConstraint(
            "origin IN ('week_order','llm','user')", name="ck_roadmap_edge_origin"
        ),
        CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_roadmap_edge_confidence"
        ),
        CheckConstraint("length(reason) <= 300", name="ck_roadmap_edge_reason"),
    )


class GraphLayout(Base):
    __tablename__ = "graph_layouts"
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    pinned: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class NodeMaterial(Base):
    """Page-level attachment contract for #114; never shared with the catalog."""

    __tablename__ = "node_materials"
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    confidence: Mapped[float] = mapped_column(default=1.0)


class Exercise(Base):
    __tablename__ = "exercises"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    origin: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resources.id", ondelete="CASCADE")
    )
    source_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("sources.id", ondelete="CASCADE")
    )
    page: Mapped[int | None] = mapped_column(Integer)
    quote_hash: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text)
    choices: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    solution_ref: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    bloom_level: Mapped[str] = mapped_column(Text, default="understand")
    license: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(Text, default="verified")
    __table_args__ = (
        CheckConstraint(
            "origin IN ('catalog','user_material')", name="ck_exercise_origin"
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_exercise_difficulty"),
        CheckConstraint(
            "type IN ('mcq','numeric','short','proof','code')", name="ck_exercise_type"
        ),
        CheckConstraint(
            "(origin = 'catalog' AND resource_id IS NOT NULL AND source_id IS NULL AND owner_id IS NULL) OR "
            "(origin = 'user_material' AND source_id IS NOT NULL AND resource_id IS NULL AND "
            "owner_id IS NOT NULL AND page IS NOT NULL AND page >= 1)",
            name="ck_exercise_source",
        ),
        CheckConstraint(
            "prompt IS NOT NULL OR location IS NOT NULL", name="ck_exercise_content"
        ),
    )


class ExerciseSubject(Base):
    __tablename__ = "exercise_subjects"
    exercise_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(
        Text, ForeignKey("subjects.id"), primary_key=True
    )


class NodeExercise(Base):
    __tablename__ = "node_exercises"
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roadmap_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    exercise_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)
    __table_args__ = (
        CheckConstraint(
            "role IN ('practice','checkpoint')", name="ck_node_exercise_role"
        ),
    )
