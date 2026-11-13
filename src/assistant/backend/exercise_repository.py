"""An exercise is shown only with source evidence, permission and current verification."""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.catalog.exercises import (
    classify,
    exact,
    extract_numbered,
    order_for,
    quote_hash,
    store_private,
)
from app.catalog.sources import load_sources
from app.catalog.taxonomy import ensure_taxonomy, save_tags, tag_resource
from app.roadmap import decode_covers

from .catalog_models import (
    Exercise,
    ExerciseSubject,
    NodeExercise,
    NodeMaterial,
    NodeSubject,
    ResourceSubject,
)
from .catalog_repository import verified_resources
from .models import Resource, RoadmapNode, Source

# A checkpoint is a test: too few questions say nothing about mastery.
REQUIRED = {"practice": 1, "checkpoint": 10}


def _sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def import_private_exercises(db, source, owner_id):
    items = store_private(
        db,
        {
            "id": source.id,
            "course_id": source.course_id,
            "text": source.text,
            "page": source.page,
        },
        owner_id,
    )
    return [db.get(Exercise, item["id"]) for item in items]


# --- catalog -------------------------------------------------------------------------


def _catalog_source(db, resource_id, now):
    """A currently verified tier 1-2 resource and its license rule (ADR 004)."""
    resource = next(
        (r for r in verified_resources(db, now) if r["id"] == resource_id), None
    )
    if resource is None or resource["tier"] > 2:
        raise ValueError("unverified_exercise_source")
    row = db.get(Resource, resource_id)
    license_rule = load_sources().licenses.get(row.license)
    if not license_rule:
        raise ValueError("missing_license_or_location")
    return row, license_rule


def import_catalog_exercise(
    db, resource_id, source_text, item, now, *, content_hash=None, page=None
):
    """Store one exercise quoted from ``source_text``, the readable text of the page.

    ``content_hash`` is the hash of the bytes that were fetched and verified; it
    defaults to hashing ``source_text`` when the two are the same.
    """
    row, license_rule = _catalog_source(db, resource_id, now)
    return _save_catalog_exercise(
        db,
        row,
        license_rule,
        source_text,
        item,
        content_hash or _sha256(source_text),
        page,
    )


def harvest_catalog_exercises(db, resource_id, pages, content_hash, now):
    """Quote every numbered exercise on a fetched, verified page (#115 step 2).

    ``pages`` is the readable text of each page; page numbers are kept only for a
    multi-page document. A source that is not verified tier 1-2 yields nothing.
    """
    try:
        row, license_rule = _catalog_source(db, resource_id, now)
    except ValueError:
        return []
    return [
        _save_catalog_exercise(
            db,
            row,
            license_rule,
            text,
            item,
            content_hash,
            number if len(pages) > 1 else None,
        )
        for number, text in enumerate(pages, start=1)
        for item in extract_numbered(text)
    ]


def _save_catalog_exercise(db, row, license_rule, source_text, item, source_hash, page):
    if row.content_hash != source_hash:
        raise ValueError("source_hash_mismatch")
    if not item.get("location"):
        raise ValueError("missing_license_or_location")
    if not exact(item, source_text):
        raise ValueError("exercise_not_in_source")
    # A link-only license keeps the exercise number and the link, never its text.
    verbatim = license_rule["verbatim"]
    choices = item.get("choices") or []
    labels = {**classify(item["prompt"], choices, item.get("answer")), **item}
    digest = quote_hash(item["prompt"], choices, item.get("answer"))
    identifier = str(uuid5(NAMESPACE_URL, row.id + ":" + digest))
    values = {
        "origin": "catalog",
        "resource_id": row.id,
        "page": page,
        "quote_hash": digest,
        "source_hash": source_hash,
        "type": labels["type"],
        "prompt": item["prompt"] if verbatim else None,
        "choices": json.dumps(choices, ensure_ascii=False) if verbatim else None,
        "answer": item.get("answer") if verbatim else None,
        "location": item["location"],
        "license": row.license,
        "solution_ref": item.get("solution_ref"),
        "difficulty": labels["difficulty"],
        "bloom_level": labels["bloom_level"],
    }
    exercise = db.get(Exercise, identifier)
    if exercise is not None:
        for key, value in values.items():
            setattr(exercise, key, value)
        db.flush()
        return exercise
    exercise = Exercise(id=identifier, **values)
    db.add(exercise)
    db.flush()
    # Tag through the same taxonomy, then copy subject IDs to the exercise.
    ensure_taxonomy(db)
    if (
        db.scalar(
            select(ResourceSubject.resource_id)
            .where(ResourceSubject.resource_id == row.id)
            .limit(1)
        )
        is None
    ):
        save_tags(db, "resource", row.id, tag_resource({"title": row.title}), row.title)
    for tag in tag_resource({"title": item["prompt"]}):
        if not tag.needs_review:
            db.add(ExerciseSubject(exercise_id=identifier, subject_id=tag.subject_id))
    return exercise


# --- reading -------------------------------------------------------------------------


def _pool_nodes(db, node):
    """A milestone's checkpoint draws on every topic it covers (the syllabus test)."""
    if node.type != "milestone":
        return [node.id]
    same_roadmap = (RoadmapNode.roadmap_id == node.roadmap_id) & (
        RoadmapNode.type == "topic"
    )
    covered = decode_covers(node.covers)
    if covered:
        query = select(RoadmapNode.id).where(same_roadmap, RoadmapNode.id.in_(covered))
    else:  # no list: a milestone covers every topic before it
        query = select(RoadmapNode.id).where(same_roadmap)
        if node.week is not None:
            query = query.where(RoadmapNode.week <= node.week)
    return [node.id, *db.scalars(query)]


def _candidate_ids(db, node_ids, role):
    linked = set(
        db.scalars(
            select(NodeExercise.exercise_id).where(
                NodeExercise.node_id.in_(node_ids), NodeExercise.role == role
            )
        )
    )
    linked.update(
        db.scalars(
            select(ExerciseSubject.exercise_id).where(
                ExerciseSubject.subject_id.in_(
                    select(NodeSubject.subject_id).where(
                        NodeSubject.node_id.in_(node_ids), NodeSubject.confidence >= 0.6
                    )
                )
            )
        )
    )
    # Exercises quoted from a page of the learner's material attached to these nodes.
    linked.update(
        db.scalars(
            select(Exercise.id)
            .join(NodeMaterial, NodeMaterial.source_id == Exercise.source_id)
            .where(NodeMaterial.node_id.in_(node_ids), NodeMaterial.confidence >= 0.6)
        )
    )
    return linked


def _private_citation(exercise, item, roadmap, course, source, source_hash):
    """Only the owner sees it, and only while the page still says it word for word."""
    if (
        exercise.owner_id != roadmap.user_id
        or not source
        or source.course_id != course.id
        or exercise.page != source.page
        or not exact(item, source.text)
        or source_hash != exercise.source_hash
    ):
        return None
    return {
        "source_id": source.id,
        "resource_id": None,
        "title": source.file_name,
        "page": source.page,
        "url": None,
        "institution": None,
        "license": "private",
    }


def _catalog_citation(exercise, item, public, licenses, original):
    """Only while the resource is verified tier 1-2 and unchanged since the quote."""
    resource = public.get(exercise.resource_id)
    if (
        not resource
        or resource["tier"] > 2
        or not original
        or original.content_hash != exercise.source_hash
        or original.license != exercise.license
    ):
        return None
    license_rule = licenses.get(original.license)
    stored_text = item["prompt"] is not None or item["choices"] or item["answer"] is not None
    if not license_rule or (not license_rule["verbatim"] and stored_text):
        return None
    citation = {k: resource.get(k) for k in ("title", "url", "institution", "license")}
    citation.update(resource_id=exercise.resource_id, source_id=None, page=exercise.page)
    return citation


def _shown(exercise, roadmap, course, public, licenses, sources, source_hashes, originals):
    """The exercise as a learner sees it, or None when its evidence does not hold."""
    item = {
        "prompt": exercise.prompt,
        "choices": json.loads(exercise.choices or "[]"),
        "answer": exercise.answer,
    }
    if exercise.origin == "user_material":
        source = sources.get(exercise.source_id)
        citation = _private_citation(
            exercise, item, roadmap, course, source, source_hashes.get(exercise.source_id)
        )
    else:
        citation = _catalog_citation(
            exercise, item, public, licenses, originals.get(exercise.resource_id)
        )
    if citation is None or (
        exercise.prompt
        and quote_hash(exercise.prompt, item["choices"], exercise.answer)
        != exercise.quote_hash
    ):
        return None
    return {
        "id": exercise.id,
        "type": exercise.type,
        "prompt": exercise.prompt,
        "choices": item["choices"],
        "difficulty": exercise.difficulty,
        "bloom_level": exercise.bloom_level,
        "auto_grade": exercise.answer is not None and exercise.prompt is not None,
        "location": exercise.location,
        "citation": citation,
    }


def exercises_for_node(db, node, roadmap, course, now, *, role="practice", limit=10):
    """Quoted exercises for a node, chosen by subject, difficulty and Bloom level.

    Too few is reported as ``insufficient``; nothing is ever written to fill the gap.
    """
    candidates = _candidate_ids(db, _pool_nodes(db, node), role)
    exercises = (
        db.scalars(
            select(Exercise).where(
                Exercise.id.in_(candidates),
                Exercise.verification_status == "verified",
            )
        ).all()
        if candidates
        else []
    )
    if not exercises:
        shown = []
    else:
        source_ids = {
            e.source_id
            for e in exercises
            if e.origin == "user_material" and e.source_id is not None
        }
        sources = (
            {
                s.id: s
                for s in db.scalars(select(Source).where(Source.id.in_(source_ids)))
            }
            if source_ids
            else {}
        )
        source_hashes = {sid: _sha256(src.text) for sid, src in sources.items()}

        if any(e.origin != "user_material" for e in exercises):
            public = {r["id"]: r for r in verified_resources(db, now)}
            licenses = load_sources().licenses
            resource_ids = {
                e.resource_id
                for e in exercises
                if e.origin != "user_material" and e.resource_id is not None
            }
            originals = (
                {
                    r.id: r
                    for r in db.scalars(
                        select(Resource).where(Resource.id.in_(resource_ids))
                    )
                }
                if resource_ids
                else {}
            )
        else:
            public, licenses, originals = {}, {}, {}

        shown = [
            value
            for exercise in exercises
            if (
                value := _shown(
                    exercise,
                    roadmap,
                    course,
                    public,
                    licenses,
                    sources,
                    source_hashes,
                    originals,
                )
            )
        ]
    result = order_for(role, shown)[:limit]
    required = REQUIRED[role]
    return {
        "node_id": node.id,
        "role": role,
        "status": "ready" if len(result) >= required else "insufficient",
        "required": required,
        "count": len(result),
        "exercises": result,
    }
