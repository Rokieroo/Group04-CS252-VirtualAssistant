"""Roadmap nodes (spec 8.3): normalize, derive from a syllabus, and link milestones.

A node is a topic to study or a milestone (an assessment) covering earlier topics.
No web or ORM types: callers pass plain values and store the returned specs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.syllabus.parse import integer, text

KINDS = ("topic", "milestone")
DEFAULT_MINUTES = {"topic": 60, "milestone": 30}
# Covered topics finish this many days before their milestone (spec 10.3.2).
MILESTONE_BUFFER_DAYS = 3
WEEK = timedelta(days=7)
_WEEK_LINE = re.compile(r"(?:week|tuần)\s*(\d+)\s*[:\-–—]\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class NodeSpec:
    kind: str
    title: str
    week: int | None = None
    duration_minutes: int | None = None
    due_at: datetime | None = None
    covers: list[str] | None = None  # None: a milestone covers every topic before it
    id: str = ""
    # Roadmap-builder metadata (issues #50 and #60). Defaults keep old callers valid.
    slug: str = ""
    difficulty: int = 1
    bloom_level: str = "understand"


def node_spec(raw: dict[str, Any]) -> NodeSpec:
    """One client node, accepting the spec's aliases (kind, est_minutes, duration)."""
    kind = text(raw.get("type") or raw.get("kind")) or "topic"
    covers = raw.get("covers")
    due_at = raw.get("due_at")
    if isinstance(due_at, datetime) and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    difficulty = integer(raw.get("difficulty")) or 1
    return NodeSpec(
        kind=kind if kind in KINDS else "topic",
        title=text(raw.get("title") or raw.get("description")) or "Untitled",
        week=integer(raw.get("week")),
        duration_minutes=integer(
            raw.get("duration_minutes") or raw.get("est_minutes") or raw.get("duration")),
        due_at=due_at,
        covers=decode_covers(covers) if isinstance(covers, str) else covers,
        slug=text(raw.get("slug")) or "",
        difficulty=min(3, max(1, difficulty)),
        bloom_level=text(raw.get("bloom_level")) or "understand",
    )


def derive_nodes(outcomes: list[str], assessments: list[tuple[str, int | None]],
                 raw_text: str) -> list[NodeSpec]:
    """A topic per learning outcome and a milestone per (name, due_week) assessment.

    A syllabus with neither falls back to its "Week N: topic, topic" lines.
    """
    nodes = [NodeSpec("topic", title) for title in outcomes]
    nodes += [NodeSpec("milestone", name, week=week) for name, week in assessments]
    return nodes or week_topics(raw_text)


def week_topics(raw_text: str) -> list[NodeSpec]:
    nodes = []
    for line in raw_text.splitlines():
        match = _WEEK_LINE.search(line.strip())
        if not match:
            continue
        week = int(match.group(1))
        for part in re.split(r"[,;|]", match.group(2)):
            title = part.strip(" .")
            if title:
                nodes.append(NodeSpec("topic", title, week=week))
    return nodes


def link(specs: list[NodeSpec]) -> list[NodeSpec]:
    """Give every node a new id and a duration; a milestone without ``covers`` covers
    all topics before it. Ids are never taken from the client."""
    linked: list[NodeSpec] = []
    topics: list[str] = []
    for spec in specs:
        covers = spec.covers
        if covers is None and spec.kind == "milestone":
            covers = list(topics)
        node = replace(spec, id=str(uuid4()), covers=covers,
                       duration_minutes=spec.duration_minutes or DEFAULT_MINUTES[spec.kind])
        linked.append(node)
        if node.kind == "topic":
            topics.append(node.id)
    return linked


def decode_covers(value: str | None) -> list[str]:
    """Stored covers are a JSON list; a client may also send "n1, n2"."""
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]


def task_due_at(due_at: datetime | None, week: int | None, now: datetime) -> datetime:
    """A node's own deadline, else the end of its week counted from ``now``."""
    return due_at or now + WEEK * max(1, week or 1)


def task_release_at(week: int | None, due_at: datetime) -> datetime | None:
    """A node with a week opens at the start of that week, one week before its
    deadline (spec 10.3.1); a node without a week can start at once."""
    return due_at - WEEK if week else None


def prerequisites(nodes: list[Any]) -> dict[str, list[str]]:
    """Milestone id -> the topic ids it covers, which must be studied first.

    Accepts NodeSpec or stored rows (``covers`` as JSON text). Only topics count, so
    a milestone never waits on another milestone and the graph cannot have a cycle.
    """
    topics = {node.id for node in nodes if node.kind == "topic"}
    needs = {}
    for node in nodes:
        if node.kind != "milestone":
            continue
        covers = node.covers
        if isinstance(covers, str):
            covers = decode_covers(covers)
        needs[node.id] = [topic for topic in covers or [] if topic in topics]
    return needs
