"""GET /today (#158): loads one learner's day as plain values for app.planner.today
and attaches the recommender's top sources to each study item. The decisions live
in app.planner.today (ADR 003)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.planner import (
    DueReview,
    LearnerDay,
    StudyNode,
    TodayItem,
    subtract,
    today,
)
from app.planner.today import REVIEW_MINUTES
from app.roadmap import Edge, prerequisites, task_due_at, task_release_at
from app.roadmap.nodes import DEFAULT_MINUTES

from .catalog_models import RoadmapEdge
from .models import (
    Availability,
    BusyBlock,
    ReviewCard,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Task,
    User,
)
from .recommendations_repository import get_or_generate_node_recommendations
from .schemas import TodayItemOut, TodayOut

SOURCES_PER_ITEM = 2
MAX_REVIEWS = 24 * 60 // REVIEW_MINUTES  # more cards than a whole day can hold never fit


def today_plan(db: Session, user: User, day: date, now: datetime) -> TodayOut:
    learner, nodes = _learner_day(db, user, day, now)
    plan = today(learner, now)
    return TodayOut(
        day=day,
        timezone=user.timezone,
        free_minutes=plan.free_minutes,
        total_minutes=plan.total_minutes,
        items=[_item_out(item, _sources(db, item, nodes, user.id, now)) for item in plan.items],
        deferred=[_item_out(item) for item in plan.deferred],
    )


def _learner_day(
    db: Session, user: User, day: date, now: datetime
) -> tuple[LearnerDay, dict[str, RoadmapNode]]:
    """The learner's current roadmaps, due reviews and free time on ``day``."""
    zone = ZoneInfo(user.timezone)
    starts = datetime.combine(day, time.min, zone)
    ends = datetime.combine(day + timedelta(days=1), time.min, zone)
    roadmaps = _current_roadmaps(db, user.id)
    nodes = list(
        db.scalars(select(RoadmapNode).where(RoadmapNode.roadmap_id.in_(roadmaps)))
    )
    tasks = {
        task.roadmap_node_id: task
        for task in db.scalars(
            select(Task).where(
                Task.assignee_id == user.id,
                Task.roadmap_node_id.in_([node.id for node in nodes]),
            )
        )
    }
    planned = list(
        db.scalars(
            select(ScheduleEntry).where(
                ScheduleEntry.user_id == user.id,
                ScheduleEntry.status == "planned",
                ScheduleEntry.starts_at < ends,
                ScheduleEntry.ends_at > starts,
            )
        )
    )
    study_tasks = {task.id for task in tasks.values()}
    planned_tasks = {entry.task_id for entry in planned}
    learner = LearnerDay(
        starts_at=starts,
        ends_at=ends,
        nodes=[
            _study_node(node, tasks.get(node.id), roadmaps[node.roadmap_id], planned_tasks)
            for node in nodes
        ],
        edges=_prerequisite_edges(db, list(roadmaps), nodes),
        reviews=[
            DueReview(card.item_id, card.due_at, card.node_id)
            for card in db.scalars(
                select(ReviewCard)
                .where(ReviewCard.user_id == user.id, ReviewCard.due_at < ends)
                .order_by(ReviewCard.due_at)
                .limit(MAX_REVIEWS)
            )
        ],
        # Sessions of other tasks are work the day already holds.
        free=subtract(
            _intervals(db, Availability, user.id, starts, ends),
            _intervals(db, BusyBlock, user.id, starts, ends)
            + [
                (entry.starts_at, entry.ends_at)
                for entry in planned
                if entry.task_id not in study_tasks
            ],
        ),
    )
    return learner, {node.id: node for node in nodes}


def _current_roadmaps(db: Session, user_id: str) -> dict[str, Roadmap]:
    """The newest roadmap of each course; older ones were regenerated away."""
    latest: dict[str, Roadmap] = {}
    for roadmap in db.scalars(
        select(Roadmap)
        .where(Roadmap.user_id == user_id)
        .order_by(Roadmap.created_at.desc())
    ):
        latest.setdefault(roadmap.course_id, roadmap)
    return {roadmap.id: roadmap for roadmap in latest.values()}


def _study_node(
    node: RoadmapNode, task: Task | None, roadmap: Roadmap, planned_tasks: set[str]
) -> StudyNode:
    """Done means completed or already known (#166). A scheduled node keeps its task's
    deadline and remaining minutes; an unscheduled one counts its weeks from the
    roadmap's creation, as scheduling would, and keeps duration.py's estimate."""
    if task is not None:
        due = task.due_at
        left = task.duration_minutes - task.completed_minutes if task.status == "pending" else 0
    else:
        due = (
            task_due_at(node.due_at, node.week, roadmap.created_at)
            if node.due_at or node.week
            else None
        )
        left = node.duration_minutes or DEFAULT_MINUTES.get(node.type, DEFAULT_MINUTES["topic"])
    return StudyNode(
        id=node.id,
        title=node.title,
        kind=node.type,
        minutes=left,
        done=node.known is not None or (task is not None and task.status == "completed"),
        due_at=due,
        release_at=task_release_at(node.week, due) if due else None,
        planned_today=task is not None and task.id in planned_tasks,
    )


def _prerequisite_edges(
    db: Session, roadmap_ids: list[str], nodes: list[RoadmapNode]
) -> list[Edge]:
    """Stored strict edges plus each milestone's covered topics, as the graph API shows them."""
    edges = [
        Edge(edge.parent_id, edge.child_id, edge.kind)
        for edge in db.scalars(
            select(RoadmapEdge).where(
                RoadmapEdge.roadmap_id.in_(roadmap_ids), RoadmapEdge.kind == "strict"
            )
        )
    ]
    return edges + [
        Edge(topic_id, milestone_id, "covers")
        for milestone_id, topic_ids in prerequisites(nodes).items()
        for topic_id in topic_ids
    ]


def _intervals(db: Session, model, user_id: str, starts: datetime, ends: datetime):
    """Availability or busy rows of ``user_id`` that overlap [starts, ends)."""
    return [
        (row.starts_at, row.ends_at)
        for row in db.scalars(
            select(model).where(
                model.user_id == user_id, model.starts_at < ends, model.ends_at > starts
            )
        )
    ]


def _sources(db: Session, item: TodayItem, nodes: dict[str, RoadmapNode], user_id: str, now: datetime):
    """The recommender's top sources for a study item (#155); reviews have none."""
    if item.kind != "study":
        return []
    return get_or_generate_node_recommendations(
        db, nodes[item.node_id], user_id, now, limit=SOURCES_PER_ITEM
    )


def _item_out(item: TodayItem, sources=()) -> TodayItemOut:
    return TodayItemOut(
        kind=item.kind,
        title=item.title,
        minutes=item.minutes,
        reason=item.reason,
        node_id=item.node_id,
        review_item_ids=list(item.item_ids),
        sources=list(sources),
    )
