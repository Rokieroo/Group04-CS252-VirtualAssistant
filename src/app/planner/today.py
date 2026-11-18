"""What to study today (#158), independent of HTTP, SQL and LLMs.

The candidates are the FSRS reviews that are due, the roadmap nodes whose
prerequisites are all done and whose week has started, and the unfinished path of
a checkpoint due within CHECKPOINT_DAYS. They are packed into the day's free time,
most urgent first. Whatever does not fit is returned as deferred and never squeezed in.
"""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from app.planner.intervals import Interval, intersect, minutes
from app.roadmap.graph import (
    PREREQUISITE_KINDS,
    edge_kind,
    edge_pair,
    learning_path,
    topological_sort,
)

REVIEW_MINUTES = 2  # one FSRS card
MIN_STUDY_MINUTES = 25  # the shortest roadmap session (spec 10.3.4)
CHECKPOINT_DAYS = 14


@dataclass(frozen=True)
class StudyNode:
    """A roadmap node as today() sees it. ``minutes`` is the study time still left."""

    id: str
    title: str
    kind: str  # "topic" or "milestone"
    minutes: int
    done: bool = False
    due_at: datetime | None = None
    release_at: datetime | None = None
    planned_today: bool = False  # the planner put a session of it on this day


@dataclass(frozen=True)
class DueReview:
    item_id: str
    due_at: datetime
    node_id: str | None = None


@dataclass(frozen=True)
class LearnerDay:
    """One learner's state for the local day [starts_at, ends_at).

    ``free`` is availability minus busy time and other planned work; it may extend
    past the day. ``edges`` take any shape app.roadmap.graph reads: only ``strict``
    and ``covers`` edges are prerequisites.
    """

    starts_at: datetime
    ends_at: datetime
    nodes: list[StudyNode]
    edges: list[Any]
    reviews: list[DueReview]
    free: list[Interval]


@dataclass(frozen=True)
class TodayItem:
    kind: str  # "review" or "study"
    title: str
    minutes: int
    reason: str
    node_id: str | None = None
    item_ids: tuple[str, ...] = ()  # the review cards


@dataclass
class TodayPlan:
    free_minutes: int
    items: list[TodayItem] = field(default_factory=list)
    deferred: list[TodayItem] = field(default_factory=list)

    @property
    def total_minutes(self) -> int:
        return sum(item.minutes for item in self.items)


def today(learner: LearnerDay, now: datetime) -> TodayPlan:
    """The day's plan. Time before ``now`` is gone, so only the rest of the day counts."""
    window = (max(learner.starts_at, now), learner.ends_at)
    free = sum(minutes(start, end) for start, end in intersect(learner.free, [window]))
    plan = TodayPlan(free_minutes=free)
    for item in _candidates(learner):
        taken = _fit(item, free - plan.total_minutes)
        if taken is None:
            plan.deferred.append(item)
        else:
            plan.items.append(taken)
    return plan


def _fit(item: TodayItem, budget: int) -> TodayItem | None:
    """The item, or the part of it that fits ``budget``; None when nothing useful fits."""
    if item.minutes <= budget:
        return item
    if item.kind == "review":
        count = budget // REVIEW_MINUTES
        if count:
            return replace(
                item,
                minutes=count * REVIEW_MINUTES,
                item_ids=item.item_ids[:count],
                reason=f"{item.reason} · hôm nay đủ thời gian cho {count}/{len(item.item_ids)} thẻ",
            )
    elif budget >= MIN_STUDY_MINUTES:
        return replace(
            item,
            minutes=budget,
            reason=f"{item.reason} · hôm nay học {budget}/{item.minutes} phút",
        )
    return None


def _candidates(learner: LearnerDay) -> list[TodayItem]:
    """Reviews, then nodes planned for today, then checkpoint paths, then the rest of
    the open nodes by deadline. A node appears once, with its most urgent reason."""
    by_id = {node.id: node for node in learner.nodes}
    unlocked, parents = _unlocked(learner.nodes, learner.edges)
    ready = [
        node
        for node in learner.nodes
        if node.id in unlocked and not node.done and node.minutes > 0
    ]
    ready_ids = {node.id for node in ready}
    study: dict[str, TodayItem] = {}

    def add(node: StudyNode, reason: str) -> None:
        if node.id in ready_ids and node.id not in study:
            study[node.id] = TodayItem("study", node.title, node.minutes, reason, node.id)

    for node in ready:
        if node.planned_today:
            add(node, "Lịch học đã xếp chặng này vào hôm nay")

    for milestone in _checkpoints(learner):
        days = _days(milestone.due_at, learner)
        path = learning_path(list(by_id), learner.edges, milestone.id)
        left = [key for key in path if not by_id[key].done and key != milestone.id]
        for key in left:
            add(by_id[key], f"{milestone.title} {_when(days)}, còn {len(left)} chặng phải học trước")
        add(milestone, f"{milestone.title} {_when(days)}: các chặng cần thiết đã xong, ôn lại trước khi kiểm tra")

    for node in sorted(ready, key=lambda n: (n.due_at is None, n.due_at or learner.ends_at)):
        if node.release_at is None or node.release_at < learner.ends_at:
            add(node, _open_reason(node, bool(parents[node.id]), learner))

    return _reviews(learner, by_id) + list(study.values())


def _unlocked(nodes: list[StudyNode], edges: list[Any]) -> tuple[set[str], dict[str, list[str]]]:
    """Nodes whose prerequisites are done at every depth, and each node's direct ones.

    Kahn's order leaves out every node on a cycle, so such a node is never unlocked.
    """
    ids = [node.id for node in nodes]
    known = set(ids)
    done = {node.id for node in nodes if node.done}
    prerequisite_edges = [edge for edge in edges if edge_kind(edge) in PREREQUISITE_KINDS]
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in prerequisite_edges:
        parent, child = edge_pair(edge)
        if parent in known and child in known:
            parents[child].append(parent)
    unlocked: set[str] = set()
    for key in topological_sort(ids, prerequisite_edges):
        if all(parent in done and parent in unlocked for parent in parents[key]):
            unlocked.add(key)
    return unlocked, parents


def _checkpoints(learner: LearnerDay) -> list[StudyNode]:
    """Unfinished milestones due from today until CHECKPOINT_DAYS after it, soonest first."""
    horizon = learner.ends_at + timedelta(days=CHECKPOINT_DAYS)
    return sorted(
        (
            node
            for node in learner.nodes
            if node.kind == "milestone"
            and not node.done
            and node.due_at is not None
            and learner.starts_at <= node.due_at < horizon
        ),
        key=lambda node: node.due_at,
    )


def _reviews(learner: LearnerDay, by_id: dict[str, StudyNode]) -> list[TodayItem]:
    """One item per node with due cards, the most overdue first."""
    groups: dict[str | None, list[DueReview]] = defaultdict(list)
    for review in sorted(learner.reviews, key=lambda r: (r.due_at, r.item_id)):
        groups[review.node_id].append(review)
    items = []
    for node_id, cards in sorted(groups.items(), key=lambda group: group[1][0].due_at):
        node = by_id.get(node_id)
        overdue = -_days(cards[0].due_at, learner)
        reason = f"{len(cards)} thẻ ôn tập đến hạn theo FSRS"
        if overdue > 0:
            reason += f", thẻ cũ nhất quá hạn {overdue} ngày"
        items.append(
            TodayItem(
                "review",
                f"Ôn tập: {node.title}" if node else "Ôn tập thẻ đến hạn",
                len(cards) * REVIEW_MINUTES,
                reason,
                node.id if node else None,
                tuple(card.item_id for card in cards),
            )
        )
    return items


def _open_reason(node: StudyNode, has_prerequisites: bool, learner: LearnerDay) -> str:
    parts = []
    if node.release_at is not None:
        parts.append("Đã đến tuần học của chặng này")
    if node.due_at is not None:
        days = _days(node.due_at, learner)
        parts.append(f"quá hạn {-days} ngày" if days < 0 else f"hạn {_when(days)}")
    if has_prerequisites:
        parts.append("các chặng tiên quyết đã xong")
    if not parts:
        parts.append("chặng tiếp theo trong lộ trình")
    reason = " · ".join(parts)
    return reason[0].upper() + reason[1:]


def _days(moment: datetime, learner: LearnerDay) -> int:
    """Calendar days from the learner's day to ``moment``, in the learner's time zone."""
    return (moment.astimezone(learner.starts_at.tzinfo).date() - learner.starts_at.date()).days


def _when(days: int) -> str:
    return "hôm nay" if days == 0 else f"còn {days} ngày"
