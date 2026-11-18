"""Placement test storage (UC-17, #166): quoted questions in, known concepts out.

The graph decisions live in :mod:`app.roadmap.placement`. This module loads a
roadmap's topics, asks the concept ranked first through a markable exercise of
the bank (#115), and writes the result to ``roadmap_nodes.known``, which the
graph shows and the planner reads to skip what the learner already knows.
"""

import json

from sqlalchemy import select

from app.roadmap.placement import MAX_QUESTIONS, mark_known, mark_unknown, place

from .catalog_models import Placement, RoadmapEdge
from .exercise_repository import markable_exercise, record_attempt
from .models import RoadmapNode


class StaleAnswer(Exception):
    """The answer is not for the question this placement is waiting on."""


def _topics(db, roadmap_id):
    """The roadmap's concepts and the strict prerequisite edges between them."""
    nodes = db.scalars(
        select(RoadmapNode).where(
            RoadmapNode.roadmap_id == roadmap_id, RoadmapNode.type == "topic"
        )
    ).all()
    edges = db.execute(
        select(RoadmapEdge.parent_id, RoadmapEdge.child_id).where(
            RoadmapEdge.roadmap_id == roadmap_id, RoadmapEdge.kind == "strict"
        )
    ).all()
    return {node.id: node for node in nodes}, [tuple(edge) for edge in edges]


def _state(placement, nodes, edges):
    return place(
        list(nodes),
        edges,
        json.loads(placement.answers),
        json.loads(placement.skipped),
        known={key for key, node in nodes.items() if node.known},
    )


def _advance(db, placement, roadmap, course, now):
    """Open the next question, or finish and record what the learner knows."""
    nodes, edges = _topics(db, roadmap.id)
    state = _state(placement, nodes, edges)
    skipped = json.loads(placement.skipped)
    question = None
    for node_id in state.candidates:
        question = markable_exercise(db, nodes[node_id], roadmap, course, now)
        if question:
            placement.node_id, placement.exercise_id = node_id, question["id"]
            break
        skipped.append(node_id)  # no exercise to ask: skip it, never guess
    placement.skipped = json.dumps(skipped)
    if question is None:
        placement.node_id = placement.exercise_id = None
        placement.finished_at = now
        for node_id in state.known:
            if nodes[node_id].known is None:
                kind = "tested" if node_id in state.tested else "inferred"
                nodes[node_id].known = kind
    return _view(placement, nodes, state, question)


def _view(placement, nodes, state, question):
    return {
        "id": placement.id,
        "roadmap_id": placement.roadmap_id,
        "status": "finished" if placement.finished_at else "active",
        "asked": len(json.loads(placement.answers)),
        "max_questions": MAX_QUESTIONS,
        "question": question
        and {
            "node_id": placement.node_id,
            "title": nodes[placement.node_id].title,
            "exercise": question,
        },
        "known": sorted(state.known),
        "unknown": sorted(state.unknown),
        "skipped": sorted(json.loads(placement.skipped)),
        # What the test saves: the roadmap's study time on concepts now known.
        "total_minutes": sum(node.duration_minutes or 0 for node in nodes.values()),
        "known_minutes": sum(nodes[key].duration_minutes or 0 for key in state.known),
    }


def start_placement(db, roadmap, course, user_id, now):
    """Resume this learner's open placement on ``roadmap`` or start a new one."""
    placement = db.scalar(
        select(Placement)
        .where(
            Placement.user_id == user_id,
            Placement.roadmap_id == roadmap.id,
            Placement.finished_at.is_(None),
        )
        .order_by(Placement.created_at.desc())
        .limit(1)
    )
    if placement is None:
        placement = Placement(user_id=user_id, roadmap_id=roadmap.id, created_at=now)
        db.add(placement)
        db.flush()
    elif placement.node_id:
        nodes, edges = _topics(db, roadmap.id)
        question = markable_exercise(
            db,
            nodes[placement.node_id],
            roadmap,
            course,
            now,
            only={placement.exercise_id},
        )
        if question:  # still visible: ask the same question again
            return _view(placement, nodes, _state(placement, nodes, edges), question)
    return _advance(db, placement, roadmap, course, now)


def answer_placement(db, placement, roadmap, course, now, exercise_id, response):
    """Mark the open question against the source's key, then advance.

    Raises StaleAnswer when ``exercise_id`` is not the open question (a double
    submit, or a question that disappeared: resuming picks a new one).
    """
    if placement.finished_at or exercise_id != placement.exercise_id:
        raise StaleAnswer
    node = db.get(RoadmapNode, placement.node_id)
    try:
        attempt = record_attempt(
            db, node, roadmap, course, now, exercise_id, placement.user_id, response
        )
    except LookupError:
        raise StaleAnswer from None
    answers = json.loads(placement.answers)
    answers[node.id] = bool(attempt["correct"])
    placement.answers = json.dumps(answers)
    return {**_advance(db, placement, roadmap, course, now), "last_attempt": attempt}


def set_known(db, node, known):
    """The learner marks or unmarks a concept; the known set stays prerequisite-closed.

    Marking also marks its prerequisites; unmarking also unmarks what depends on
    it. Returns the IDs whose state changed.
    """
    if node.type != "topic":
        raise ValueError("only a concept can be known")
    nodes, edges = _topics(db, node.roadmap_id)
    before = {key for key, row in nodes.items() if row.known}
    update = mark_known if known else mark_unknown
    after = update(list(nodes), edges, before, node.id)
    for key in before - after:
        nodes[key].known = None
    for key in after - before:
        nodes[key].known = "learner"
    return sorted(before ^ after)
