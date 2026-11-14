"""Build a roadmap graph from normalized topics and syllabus milestones (spec 10.1).

The builder is deliberately pure: it accepts plain values, an optional LLM client and
an injectable ``now``. That keeps the API, CLI and tests on one code path while no
network call happens unless a client is passed in.

Strict prerequisite edges come from ``prompts/prereq_v1.txt``. The prompt answer is
validated, filtered at ``confidence >= 0.6`` and repaired with Tarjan SCC before the
Kahn order is returned, so a bad LLM answer can never make the roadmap unusable.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from app.concepts import TopicIn, comparison_key, normalize_topics, slugify
from app.llm import LLMClient, RetryableError
from app.llm.blocks import BLOCKS
from app.roadmap.duration import allocate_durations, weekly_minutes
from app.roadmap.graph import Edge, find_cycles, node_key, topological_sort
from app.roadmap.nodes import NodeSpec, decode_covers
from app.syllabus import AssessmentItem
from app.syllabus.parse import integer, text

log = logging.getLogger("app.roadmap")

PROMPTS = Path(__file__).parent / "prompts"
PREREQ_PROMPT = "prereq_v1"
STRICT_CONFIDENCE = 0.6
WEEK = timedelta(days=7)

PREREQ_SCHEMA = {
    "type": "object",
    "properties": {
        "prerequisites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parent_slug": {"type": "string"},
                    "child_slug": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["parent_slug", "child_slug", "confidence"],
            },
        }
    },
    "required": ["prerequisites"],
}


@dataclass(frozen=True)
class Roadmap:
    """A built roadmap: nodes, accepted edges and the repair history."""

    nodes: list[NodeSpec]
    edges: list[Edge]
    order: list[str]
    errors: list[str]
    cycles: list[Edge]
    removed_edges: list[Edge]
    # Strict edges below STRICT_CONFIDENCE: shown as suggestions, never enforced.
    suggested_edges: list[Edge] = field(default_factory=list)

    @property
    def topics(self) -> list[NodeSpec]:
        return [node for node in self.nodes if node.kind == "topic"]

    @property
    def milestones(self) -> list[NodeSpec]:
        return [node for node in self.nodes if node.kind == "milestone"]

    def edges_of(self, kind: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.kind == kind]


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    else:
        try:
            moment = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _topic_value(topic: Any, key: str, default: Any = None) -> Any:
    if isinstance(topic, dict):
        return topic.get(key, default)
    return getattr(topic, key, default)


def _topic_rows(topics: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize topics through #50, keeping the builder-only metadata."""
    pending: list[TopicIn] = []
    extras: list[dict[str, Any]] = []
    for topic in topics:
        if isinstance(topic, TopicIn):
            title, week = topic.title, topic.week
            source_page, summary = topic.source_page, topic.summary
            slug = ""
        else:
            title = text(
                _topic_value(topic, "title")
                or _topic_value(topic, "description")
                or _topic_value(topic, "name")
            ) or "Untitled"
            week = integer(_topic_value(topic, "week")) or 1
            source_page = _topic_value(topic, "source_page")
            summary = text(_topic_value(topic, "summary")) or ""
            slug = text(_topic_value(topic, "slug")) or ""
        pending.append(TopicIn(title, week, source_page, summary))
        extras.append(
            {
                "slug": slug,
                "week": week,
                "difficulty": integer(_topic_value(topic, "difficulty")) or 1,
                "bloom_level": text(_topic_value(topic, "bloom_level")) or "understand",
                "due_at": _as_datetime(_topic_value(topic, "due_at")),
            }
        )

    normalized = normalize_topics(pending)
    title_extras: dict[str, dict[str, Any]] = {}
    for item, extra in zip(pending, extras, strict=True):
        key = comparison_key(item.title)
        current = title_extras.get(key)
        # Normalization keeps the earliest duplicate, so keep its metadata too.
        if current is None or int(extra["week"]) < int(current["week"]):
            title_extras[key] = extra

    used: set[str] = set()
    rows = []
    for item in normalized:
        extra = title_extras.get(comparison_key(item["title"]), {})
        slug = extra.get("slug") or item["slug"]
        if slug in used:
            slug = item["slug"]
        base, suffix = slug, 2
        while slug in used:
            slug = f"{base}-{suffix}"
            suffix += 1
        used.add(slug)
        rows.append(
            {
                **item,
                "slug": slug,
                "difficulty": min(3, max(1, int(extra.get("difficulty") or 1))),
                "bloom_level": extra.get("bloom_level") or "understand",
                "due_at": extra.get("due_at"),
            }
        )
    return rows


def _coerce_milestone(milestone: Any) -> dict[str, Any]:
    if isinstance(milestone, AssessmentItem):
        title, week = milestone.name, milestone.due_week
        due_at, covers = None, None
    else:
        title = text(
            _topic_value(milestone, "title")
            or _topic_value(milestone, "name")
            or _topic_value(milestone, "description")
        ) or "Milestone"
        week = integer(
            _topic_value(milestone, "week") or _topic_value(milestone, "due_week")
        )
        due_at = _as_datetime(_topic_value(milestone, "due_at"))
        covers = _topic_value(milestone, "covers")
        if isinstance(covers, str):
            covers = decode_covers(covers)
    return {
        "title": title,
        "week": week,
        "due_at": due_at,
        "covers": list(covers) if covers else None,
    }


def _milestone_id(title: str, week: int | None) -> str:
    slug = slugify(title) or "milestone"
    return f"milestone-{week}-{slug}" if week else f"milestone-{slug}"


def _unique_id(base: str, used: set[str]) -> str:
    candidate, suffix = base, 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _resolve_topic(value: Any, by_id: dict[str, NodeSpec]) -> list[str]:
    """Resolve an explicit cover value to one or more topic ids."""
    raw = str(value).strip()
    candidates = [raw, raw.strip('"').strip("'")]
    for candidate in candidates:
        if candidate in by_id:
            return [candidate]
    slug = slugify(raw)
    if slug in by_id:
        return [slug]
    for node in by_id.values():
        if node.slug == raw or node.slug == slug:
            return [node.id]
    return [
        node.id
        for node in by_id.values()
        if comparison_key(node.title) == comparison_key(raw)
    ]


def _assign_covers(
    topics: list[NodeSpec], milestones: list[dict[str, Any]]
) -> dict[str, list[str]]:
    by_id = {topic.id: topic for topic in topics}
    ids = list(by_id)
    covered: dict[str, list[str]] = {}
    previous_week = 0
    for milestone in sorted(
        milestones, key=lambda item: (item["week"] or 0, item["index"])
    ):
        explicit = milestone["covers"]
        if explicit:
            found: list[str] = []
            for value in explicit:
                for topic_id in _resolve_topic(value, by_id):
                    if topic_id not in found:
                        found.append(topic_id)
            covered[milestone["id"]] = found
        elif milestone["week"] is None:
            covered[milestone["id"]] = ids[:]
        else:
            week = milestone["week"]
            found = [
                topic.id for topic in topics
                if previous_week < (topic.week or 1) <= week
            ]
            covered[milestone["id"]] = found
            previous_week = max(previous_week, week)
        if milestone["week"] is not None:
            previous_week = max(previous_week, milestone["week"])
    return covered


def _coerce_edge(edge: Any) -> Edge | None:
    if isinstance(edge, Edge):
        return edge
    if isinstance(edge, dict):
        parent = edge.get("parent_slug") or edge.get("parent") or edge.get("source")
        child = edge.get("child_slug") or edge.get("child") or edge.get("target")
        if not parent or not child:
            return None
        kind = str(edge.get("kind") or edge.get("type") or "strict")
        return Edge(
            parent=str(parent),
            child=str(child),
            kind=kind,
            confidence=_confidence(edge.get("confidence", 1.0)),
            reason=str(edge.get("reason") or ""),
        )
    if isinstance(edge, (tuple, list)):
        if len(edge) < 2:
            return None
        kind, confidence = "strict", 1.0
        if len(edge) > 2 and isinstance(edge[2], (int, float)):
            confidence = _confidence(edge[2])
        elif len(edge) > 2:
            kind = str(edge[2])
            if len(edge) > 3:
                confidence = _confidence(edge[3])
        return Edge(str(edge[0]), str(edge[1]), kind, confidence)
    parent = getattr(edge, "parent", None) or getattr(edge, "source", None)
    child = getattr(edge, "child", None) or getattr(edge, "target", None)
    if not parent or not child:
        return None
    return Edge(
        parent=str(parent),
        child=str(child),
        kind=str(getattr(edge, "kind", "strict") or "strict"),
        confidence=_confidence(getattr(edge, "confidence", 1.0)),
        reason=str(getattr(edge, "reason", "") or ""),
    )


def _confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def parse_prerequisites(answer: str, valid_slugs: Iterable[str]) -> list[Edge]:
    """Validate an LLM answer, dropping unknown topics and self-loops.

    Confidence is clamped to 0..1 here; the 0.6 threshold is a builder decision so
    callers can inspect weaker proposals during review.
    """
    try:
        data = json.loads(answer)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        rows = (
            data.get("prerequisites")
            or data.get("relationships")
            or data.get("edges")
            or []
        )
    else:
        rows = data
    if not isinstance(rows, list):
        return []

    valid = set(valid_slugs)
    canonical = {slug: slug for slug in valid}
    canonical.update({slugify(slug): slug for slug in valid})
    found: dict[tuple[str, str], Edge] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        parent = str(row.get("parent_slug") or row.get("parent") or "").strip()
        child = str(row.get("child_slug") or row.get("child") or "").strip()
        parent = canonical.get(parent, canonical.get(slugify(parent), ""))
        child = canonical.get(child, canonical.get(slugify(child), ""))
        if not parent or not child or parent == child:
            continue
        confidence = _confidence(row.get("confidence", 0.0))
        edge = Edge(
            parent=parent,
            child=child,
            kind="strict",
            confidence=confidence,
            reason=str(row.get("reason") or "").strip()[:240],
        )
        pair = (parent, child)
        if pair not in found or confidence > found[pair].confidence:
            found[pair] = edge
    return list(found.values())


def propose_prerequisites(
    llm: LLMClient,
    topics: Iterable[Any],
    *,
    min_confidence: float = 0.0,
) -> list[Edge]:
    """Ask the configured LLM for strict prerequisite edges.

    Bad JSON, network errors and quota failures are logged and become ``[]``. The
    roadmap still works with week-order edges, which is the required fallback.
    """
    rows = [
        {
            "slug": node_key(topic),
            "title": str(_topic_value(topic, "title", "") or ""),
            "week": integer(_topic_value(topic, "week")) or 1,
            "summary": str(_topic_value(topic, "summary", "") or ""),
        }
        for topic in topics
    ]
    if not rows:
        return []
    listing = "\n".join(
        f"{row['slug']} | {row['title']} | week {row['week']} | {row['summary']}"
        for row in rows
    )
    try:
        answer = llm.complete(
            BLOCKS.wrap("candidates", listing),
            system=_prompt(PREREQ_PROMPT),
            json_schema=PREREQ_SCHEMA,
            max_tokens=4096,
            temperature=0.0,
        ).text
    except (RetryableError, ValueError, TypeError) as exc:
        log.warning("roadmap: prerequisite prompt failed: %s", exc)
        return []
    edges = parse_prerequisites(answer, [row["slug"] for row in rows])
    return [edge for edge in edges if edge.confidence >= min_confidence]


def _soft_edges(topics: list[NodeSpec]) -> list[Edge]:
    """Connect the last topic of a week to the first topic of the next week."""
    weeks = sorted({topic.week or 1 for topic in topics})
    result = []
    for earlier, later in pairwise(weeks):
        left = [topic for topic in topics if (topic.week or 1) == earlier]
        right = [topic for topic in topics if (topic.week or 1) == later]
        if left and right:
            result.append(
                Edge(
                    parent=left[-1].id,
                    child=right[0].id,
                    kind="soft",
                    confidence=1.0,
                    reason=f"week {earlier} -> week {later}",
                )
            )
    return result


def _dedupe_edges(edges: list[Edge]) -> list[Edge]:
    """Keep one edge per pair; a strict prerequisite wins over the soft week edge."""
    result: dict[tuple[str, str], Edge] = {}
    for edge in edges:
        pair = (edge.parent, edge.child)
        current = result.get(pair)
        if current is None or (current.kind == "soft" and edge.kind == "strict"):
            result[pair] = edge
    return list(result.values())


def _repair_cycles(
    nodes: list[NodeSpec], edges: list[Edge]
) -> tuple[list[Edge], list[Edge], list[Edge], list[str]]:
    """Remove one edge per cycle, preferring the least confident strict edge."""
    cycles: list[Edge] = []
    removed: list[Edge] = []
    errors: list[str] = []
    remaining = list(edges)
    for _ in range(len(edges) + 1):
        found = find_cycles(nodes, remaining)
        if not found:
            break
        for edge in found:
            if edge not in cycles:
                cycles.append(edge)
        candidates = [edge for edge in found if edge.kind == "strict"] or found
        victim = min(candidates, key=lambda edge: (edge.confidence, edge.parent, edge.child))
        remaining = [
            edge
            for edge in remaining
            if (edge.parent, edge.child) != (victim.parent, victim.child)
        ]
        removed.append(victim)
        errors.append(
            f"removed {victim.kind} edge {victim.parent} -> {victim.child} "
            f"to break a dependency cycle"
        )
    if find_cycles(nodes, remaining):
        errors.append("dependency cycle could not be repaired")
    return remaining, cycles, removed, errors


def _due_at_for(week: int | None, now: datetime) -> datetime:
    return now + WEEK * max(1, week or 1)


def build_roadmap(
    topics: Iterable[Any],
    milestones: Iterable[Any] | None = None,
    llm: LLMClient | None = None,
    *,
    credits: float = 3,
    weekly_budget: int | None = None,
    prereq_edges: Iterable[Any] | None = None,
    now: datetime | None = None,
    review_bonus: float = 0.20,
    milestone_buffer_days: int = 0,
) -> Roadmap:
    """Create topic/milestone nodes, week and prerequisite edges, durations and dates.

    ``topics`` may be the dictionaries returned by ``normalize_topics`` (#50), plain
    ``TopicIn`` objects or ``NodeSpec`` rows. ``milestones`` may be assessments from
    the syllabus, dictionaries or node specs. ``llm`` is optional: without it only
    deterministic week-order edges are created.
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)

    rows = _topic_rows(topics)
    used_ids: set[str] = set()
    topic_nodes: list[NodeSpec] = []
    for row in rows:
        due_at = row["due_at"] or _due_at_for(row["week"], moment)
        topic_nodes.append(
            NodeSpec(
                kind="topic",
                title=row["title"],
                week=row["week"],
                due_at=due_at,
                id=_unique_id(row["slug"], used_ids),
                slug=row["slug"],
                difficulty=row["difficulty"],
                bloom_level=row["bloom_level"],
            )
        )
    by_id = {topic.id: topic for topic in topic_nodes}

    milestone_rows = []
    for index, milestone in enumerate(milestones or []):
        item = _coerce_milestone(milestone)
        item["index"] = index
        item["id"] = _unique_id(_milestone_id(item["title"], item["week"]), used_ids)
        milestone_rows.append(item)

    covers = _assign_covers(topic_nodes, milestone_rows)
    milestone_nodes: list[NodeSpec] = []
    for item in sorted(milestone_rows, key=lambda row: (row["week"] or 0, row["index"])):
        due_at = item["due_at"] or _due_at_for(item["week"], moment)
        covered = covers.get(item["id"], [])
        for topic_id in covered:
            topic = by_id.get(topic_id)
            if topic is None or topic.due_at is None:
                continue
            latest = due_at - timedelta(days=max(0, milestone_buffer_days))
            if topic.due_at > latest:
                topic = replace(topic, due_at=latest)
                by_id[topic_id] = topic
                topic_nodes = [topic if node.id == topic_id else node for node in topic_nodes]
        milestone_nodes.append(
            NodeSpec(
                kind="milestone",
                title=item["title"],
                week=item["week"],
                due_at=due_at,
                covers=covered,
                id=item["id"],
                slug=slugify(item["title"]) or "milestone",
            )
        )

    nodes = topic_nodes + milestone_nodes
    edges = _soft_edges(topic_nodes)
    proposed = list(prereq_edges) if prereq_edges is not None else (
        propose_prerequisites(llm, topic_nodes) if llm is not None else []
    )
    suggested_edges: list[Edge] = []
    for raw in proposed:
        edge = _coerce_edge(raw)
        if edge is None or edge.parent not in by_id or edge.child not in by_id                 or edge.parent == edge.child:
            continue
        if edge.kind == "strict" and edge.confidence < STRICT_CONFIDENCE:
            suggested_edges.append(edge)  # the learner confirms it on the graph (#97)
            continue
        edges.append(edge)
    edges = _dedupe_edges(edges)
    edges, cycles, removed, errors = _repair_cycles(nodes, edges)

    durations = allocate_durations(
        topic_nodes,
        weekly_budget=weekly_budget if weekly_budget is not None else weekly_minutes(credits),
        milestones=milestone_nodes,
        review_bonus=review_bonus,
    )
    topic_nodes = [
        replace(node, duration_minutes=durations.get(node.id, 0)) for node in topic_nodes
    ]
    milestone_nodes = [
        replace(node, duration_minutes=durations.get(node.id, 0)) for node in milestone_nodes
    ]
    nodes = topic_nodes + milestone_nodes
    return Roadmap(
        nodes=nodes,
        edges=edges,
        order=topological_sort(nodes, edges),
        errors=errors,
        cycles=cycles,
        removed_edges=removed,
        suggested_edges=suggested_edges,
    )


build = build_roadmap
