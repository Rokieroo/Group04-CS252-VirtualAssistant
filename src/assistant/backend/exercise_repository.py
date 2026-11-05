"""An exercise is shown only with source evidence, permission and current verification."""

import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml
from sqlalchemy import select

from app.catalog.exercises import exact, quote_hash, store_private
from app.catalog.taxonomy import ensure_taxonomy, save_tags, tag_resource

from .catalog_models import (
    Exercise,
    ExerciseSubject,
    NodeExercise,
    NodeSubject,
    ResourceSubject,
)
from .catalog_repository import verified_resources
from .models import Source

POLICY = Path(__file__).resolve().parents[3] / "data/policy/catalog_sources.yaml"


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


def import_catalog_exercise(db, resource_id, source_text, item, now):
    resource = next(
        (r for r in verified_resources(db, now) if r["id"] == resource_id), None
    )
    if resource is None or resource["tier"] > 2:
        raise ValueError("unverified_exercise_source")
    from .models import Resource

    row = db.get(Resource, resource_id)
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    if row.content_hash != source_hash:
        raise ValueError("source_hash_mismatch")
    license_rule = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["licenses"].get(
        row.license
    )
    if not license_rule or not item.get("location"):
        raise ValueError("missing_license_or_location")
    if not exact(item, source_text):
        raise ValueError("exercise_not_in_source")
    verbatim = license_rule["verbatim"]
    digest = quote_hash(item["prompt"], item.get("choices", []), item.get("answer"))
    identifier = str(uuid5(NAMESPACE_URL, resource_id + ":" + digest))
    exercise = db.get(Exercise, identifier)
    values = {
        "origin": "catalog",
        "resource_id": resource_id,
        "quote_hash": digest,
        "source_hash": source_hash,
        "type": item.get("type", "short"),
        "prompt": item["prompt"] if verbatim else None,
        "choices": json.dumps(item.get("choices", [])) if verbatim else None,
        "answer": item.get("answer") if verbatim else None,
        "location": item["location"],
        "license": row.license,
        "solution_ref": item.get("solution_ref"),
        "difficulty": item.get("difficulty", 1),
        "bloom_level": item.get("bloom_level", "understand"),
    }
    if exercise is not None:
        for key, value in values.items():
            setattr(exercise, key, value)
        db.flush()
        return exercise
    exercise = Exercise(id=identifier, **values)
    db.add(exercise)
    db.flush()
    # Tag through the same taxonomy, then copy subject IDs to the exercise.
    tags = tag_resource({"title": item["prompt"]})
    ensure_taxonomy(db)
    if (
        db.scalar(
            select(ResourceSubject.resource_id)
            .where(ResourceSubject.resource_id == resource_id)
            .limit(1)
        )
        is None
    ):
        save_tags(
            db, "resource", resource_id, tag_resource({"title": row.title}), row.title
        )
    for tag in tags:
        if not tag.needs_review:
            db.add(ExerciseSubject(exercise_id=identifier, subject_id=tag.subject_id))
    return exercise


def exercises_for_node(db, node, roadmap, course, now, *, role="practice", limit=10):
    subjects = set(
        db.scalars(
            select(NodeSubject.subject_id).where(
                NodeSubject.node_id == node.id, NodeSubject.confidence >= 0.6
            )
        )
    )
    linked = set(
        db.scalars(
            select(NodeExercise.exercise_id).where(
                NodeExercise.node_id == node.id, NodeExercise.role == role
            )
        )
    )
    if subjects:
        linked.update(
            db.scalars(
                select(ExerciseSubject.exercise_id).where(
                    ExerciseSubject.subject_id.in_(subjects)
                )
            )
        )
    public = {r["id"]: r for r in verified_resources(db, now)}
    licenses = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["licenses"]
    result = []
    for exercise in db.scalars(
        select(Exercise)
        .where(Exercise.id.in_(linked), Exercise.verification_status == "verified")
        .order_by(Exercise.difficulty, Exercise.id)
    ):
        choices = json.loads(exercise.choices or "[]")
        item = {
            "prompt": exercise.prompt,
            "choices": choices,
            "answer": exercise.answer,
        }
        if exercise.origin == "user_material":
            source = db.get(Source, exercise.source_id)
            if (
                exercise.owner_id != roadmap.user_id
                or not source
                or source.course_id != course.id
                or exercise.page != source.page
                or not exact(item, source.text)
                or hashlib.sha256(source.text.encode()).hexdigest()
                != exercise.source_hash
            ):
                continue
            citation = {
                "source_id": source.id,
                "resource_id": None,
                "title": source.file_name,
                "page": source.page,
                "url": None,
                "institution": None,
                "license": "private",
            }
        else:
            resource = public.get(exercise.resource_id)
            from .models import Resource

            original = db.get(Resource, exercise.resource_id)
            if (
                not resource
                or resource["tier"] > 2
                or not original
                or original.content_hash != exercise.source_hash
                or original.license != exercise.license
            ):
                continue
            license_rule = licenses.get(original.license)
            if not license_rule or (
                not license_rule["verbatim"]
                and (
                    exercise.prompt is not None
                    or choices
                    or exercise.answer is not None
                )
            ):
                continue
            citation = {
                k: resource.get(k) for k in ("title", "url", "institution", "license")
            }
            citation.update(
                resource_id=exercise.resource_id, source_id=None, page=exercise.page
            )
        if (
            exercise.prompt
            and quote_hash(exercise.prompt, choices, exercise.answer)
            != exercise.quote_hash
        ):
            continue
        result.append(
            {
                "id": exercise.id,
                "type": exercise.type,
                "prompt": exercise.prompt,
                "choices": choices,
                "difficulty": exercise.difficulty,
                "bloom_level": exercise.bloom_level,
                "auto_grade": exercise.answer is not None
                and exercise.prompt is not None,
                "location": exercise.location,
                "citation": citation,
            }
        )
        if len(result) == limit:
            break
    required = 10 if role == "checkpoint" else 1
    return {
        "node_id": node.id,
        "role": role,
        "status": "ready" if len(result) >= required else "insufficient",
        "required": required,
        "count": len(result),
        "exercises": result,
    }
