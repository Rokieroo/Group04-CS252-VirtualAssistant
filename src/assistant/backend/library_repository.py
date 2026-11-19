"""A learner's personal library (UC-15): pinned, hidden and annotated node sources.

Rows hang off ``roadmap_nodes``, so ownership follows the node's roadmap and course;
callers check that the learner owns the node before an edit.
"""

from datetime import datetime

from sqlalchemy import select, update

from .catalog_repository import node_sources, verified_resource_map
from .models import Course, PersonalSource, Roadmap, RoadmapNode, Source


def personal_states(db, node_id: str) -> dict[str, str]:
    """``source_key -> state`` for one node, to mark the sources a learner sees."""
    return dict(
        db.execute(
            select(PersonalSource.source_key, PersonalSource.state).where(
                PersonalSource.node_id == node_id
            )
        ).all()
    )


def library_items(db, user_id: str, now: datetime) -> list[dict]:
    """Every personal source of a learner, with the node and course it belongs to."""
    rows = (
        db.execute(
            select(
                PersonalSource.node_id,
                RoadmapNode.title.label("node_title"),
                Course.id.label("course_id"),
                Course.title.label("course_title"),
                Roadmap.id.label("roadmap_id"),
                PersonalSource.source_key,
                PersonalSource.title,
                PersonalSource.state,
                PersonalSource.note,
                Source.page,
            )
            .select_from(PersonalSource)
            .join(RoadmapNode)
            .join(Roadmap)
            .join(Course)
            # The learner's own material is a page of a course source; the rest are catalog resources.
            .outerjoin(
                Source,
                (Source.id == PersonalSource.source_key) & (Source.course_id == Course.id),
            )
            .where(Roadmap.user_id == user_id, Course.owner_id == user_id)
            .order_by(Course.title, RoadmapNode.title, PersonalSource.title)
        )
        .mappings()
        .all()
    )
    urls = (
        verified_resource_map(db, now, [r.source_key for r in rows if r.page is None])
        if any(r.page is None for r in rows)
        else {}
    )
    return [dict(r, url=urls.get(r.source_key) if r.page is None else None) for r in rows]


def edit_library(
    db, node, roadmap, course, source_key: str, state: str | None, note: str | None, now
) -> bool:
    """Apply a pin/hide/note change; False when the source is not offered on the node.

    A row with no state and no note is deleted, so the table holds only real choices.
    """
    # Lock the node row so a first insert and a concurrent partial update serialize.
    db.execute(update(RoadmapNode).where(RoadmapNode.id == node.id).values(title=RoadmapNode.title))
    row = db.get(PersonalSource, (node.id, source_key))
    if row is None:
        offered = node_sources(db, [node], roadmap, course, now)[node.id]["sources"]
        source = next((s for s in offered if s["id"] == source_key), None)
        if source is None:
            return False
        row = PersonalSource(
            node_id=node.id, source_key=source_key, title=source["title"], state="none", note=""
        )
    if state is not None:
        row.state = state
    if note is not None:
        row.note = note.strip()
    if row.state == "none" and not row.note:
        if row in db:
            db.delete(row)
    else:
        db.add(row)
    return True
