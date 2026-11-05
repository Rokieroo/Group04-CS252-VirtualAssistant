"""Subject tagging jobs (issue #99): store app.taxonomy labels on nodes and resources.

``tag_roadmap`` runs once a roadmap is generated (#60) and again, a few times, while a
stage it needed keeps failing. ``tag_resources`` runs when the search job creates
resources, and once a day for anything still untagged, such as rows a catalog
connector ingested (#98) or a resource whose tagging failed. Labels below ``REVIEW_CONFIDENCE`` wait in
``review_queue`` for a reviewer (#101); a reviewer's label has method "manual".

Both handlers are safe to repeat (jobs are delivered at least once): they replace an
item's machine labels and never touch a reviewer's.
"""

import json
from datetime import datetime, timedelta
from functools import cache
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.llm import get_client, get_embedder
from app.roadmap import decode_covers
from app.taxonomy import (
    REVIEW_CONFIDENCE,
    NodeText,
    ResourceText,
    Tagger,
    Tagging,
    Taxonomy,
)

from .jobs import enqueue, handler
from .models import (
    CatalogCourse,
    CatalogUnit,
    Course,
    NodeSubject,
    Resource,
    ResourceSubject,
    Roadmap,
    RoadmapNode,
    Subject,
)
from .services import course_outcomes

BATCH = 50  # resources per sweep job: one embedding request, at most 3 LLM prompts
MANUAL = "manual"
NODE_RETRIES = 3  # then the nodes keep their rule labels and go without a vector
NODE_RETRY_DELAY = timedelta(minutes=30)  # doubles; outlasts a per-minute quota


@cache
def _shared_tagger() -> Tagger:
    """One per process, so the taxonomy is embedded once rather than in every job."""
    return Tagger(embedder=get_embedder(), llm=get_client())


make_tagger = _shared_tagger  # seam for tests and vendor swaps


def sync_subjects(db: Session, taxonomy: Taxonomy) -> dict[str, str]:
    """Bring ``subjects`` in line with the YAML; return slug -> id.

    Retired slugs stay: labels may still point at them.
    """
    rows = {row.slug: row for row in db.scalars(select(Subject))}
    for entry in taxonomy:  # a parent always comes before its children
        row = rows.get(entry.slug)
        if row is None:
            row = rows[entry.slug] = Subject(id=str(uuid4()), slug=entry.slug)
            db.add(row)
        row.name, row.name_vi = entry.name, entry.name_vi
        row.parent_id = rows[entry.parent].id if entry.parent else None
    db.flush()
    return {slug: row.id for slug, row in rows.items()}


def review_queue(db: Session, limit: int = 100) -> list[tuple[ResourceSubject, str]]:
    """Machine labels on resources a reviewer should confirm, least sure first."""
    return list(db.execute(
        select(ResourceSubject, Subject.slug)
        .join(Subject, Subject.id == ResourceSubject.subject_id)
        .where(ResourceSubject.confidence < REVIEW_CONFIDENCE,
               ResourceSubject.method != MANUAL)
        .order_by(ResourceSubject.confidence, ResourceSubject.resource_id)
        .limit(limit)
    ))


@handler("tag_roadmap")
def tag_roadmap(db: Session, payload: dict, now: datetime) -> dict:
    """Label every node of ``payload["roadmap_id"]``; ``payload["retry"]`` counts reruns.

    Labels are stored even when a stage failed, so nodes are never left bare; the
    rerun replaces them and adds the missing vectors.
    """
    roadmap = db.get(Roadmap, payload["roadmap_id"])
    if roadmap is None:
        return {"status": "roadmap_deleted"}
    course = db.get(Course, roadmap.course_id)
    nodes = list(db.scalars(select(RoadmapNode).where(RoadmapNode.roadmap_id == roadmap.id)
                            .order_by(RoadmapNode.id)))
    titles = {node.id: node.title for node in nodes}
    outcomes = course_outcomes(db, course.id)
    texts = [
        NodeText(node.title, outcomes, course.title,
                 tuple(titles[i] for i in decode_covers(node.covers) if i in titles),
                 course.level)
        for node in nodes
    ]
    tagger = make_tagger()
    ids = sync_subjects(db, tagger.taxonomy)
    taggings = tagger.tag_nodes(texts)
    for node, tagging in zip(nodes, taggings):
        _replace_labels(db, NodeSubject, NodeSubject.node_id, node.id, tagging, ids)
        _keep_vector(node, tagging, tagger)
    retry = payload.get("retry", 0)
    if retry < NODE_RETRIES and not all(t.complete for t in taggings):
        enqueue(db, "tag_roadmap", {"roadmap_id": roadmap.id, "retry": retry + 1}, now=now,
                run_after=now + NODE_RETRY_DELAY * 2 ** retry, user_id=roadmap.user_id)
    return _summary(taggings)


@handler("tag_resources")
def tag_resources(db: Session, payload: dict, now: datetime) -> dict:
    """Label ``payload["resource_ids"]``, or sweep untagged resources in id order.

    A sweep job takes ``BATCH`` resources after ``payload["after"]`` and chains the
    next batch, so the backlog drains in one pass. A resource whose tagging was
    incomplete (the LLM or embedder failed) keeps ``tagged_at`` empty: the next
    day's sweep tries it again, and it never holds up the rest of today's pass.
    """
    given = payload.get("resource_ids")
    query = select(Resource).order_by(Resource.id)
    if given:
        query = query.where(Resource.id.in_(given))
    else:
        query = query.where(Resource.tagged_at.is_(None)).limit(BATCH)
        if payload.get("after"):
            query = query.where(Resource.id > payload["after"])
    resources = list(db.scalars(query))
    courses = _catalog_courses(db, [resource.id for resource in resources])
    level = payload.get("level", "university")
    texts = [_resource_text(resource, courses.get(resource.id), level) for resource in resources]
    tagger = make_tagger()
    ids = sync_subjects(db, tagger.taxonomy)
    taggings = tagger.tag_resources(texts)
    for resource, tagging in zip(resources, taggings):
        _replace_labels(db, ResourceSubject, ResourceSubject.resource_id, resource.id, tagging, ids)
        _keep_vector(resource, tagging, tagger)
        if tagging.complete:
            resource.tagged_at = now
    if not given and len(resources) == BATCH:
        enqueue(db, "tag_resources", {"after": resources[-1].id}, now=now)
    return _summary(taggings)


def _resource_text(resource: Resource, course: CatalogCourse | None, level: str) -> ResourceText:
    if course is None:
        return ResourceText(resource.title, resource.url, level=level)
    return ResourceText(resource.title, resource.url, course_code=course.code or "",
                        course_title=course.title,
                        level="k12" if course.level == "k12" else "university")


def _catalog_courses(db: Session, resource_ids: list[str]) -> dict[str, CatalogCourse]:
    """resource id -> a catalog course it is a unit of (the first one by id)."""
    rows = db.execute(
        select(CatalogUnit.resource_id, CatalogCourse)
        .join(CatalogCourse, CatalogCourse.id == CatalogUnit.course_id)
        .where(CatalogUnit.resource_id.in_(resource_ids))
        .order_by(CatalogCourse.id)
    )
    courses: dict[str, CatalogCourse] = {}
    for resource_id, course in rows:
        courses.setdefault(resource_id, course)
    return courses


def _replace_labels(db: Session, model, owner, owner_id: str, tagging: Tagging,
                    ids: dict[str, str]) -> None:
    reviewed = set(db.scalars(select(model.subject_id)
                              .where(owner == owner_id, model.method == MANUAL)))
    db.execute(delete(model).where(owner == owner_id, model.method != MANUAL))
    for tag in tagging.tags:
        if ids[tag.slug] not in reviewed:
            db.add(model(**{owner.key: owner_id}, subject_id=ids[tag.slug],
                         confidence=tag.confidence, method=tag.method))


def _keep_vector(row: Resource | RoadmapNode, tagging: Tagging, tagger: Tagger) -> None:
    if tagging.embedding is not None:
        row.embedding = json.dumps([round(value, 6) for value in tagging.embedding])
        row.embedding_model = tagger.embedder.model


def _summary(taggings: list[Tagging]) -> dict:
    return {
        "tagged": len(taggings),
        "labelled": sum(any(not tag.needs_review for tag in t.tags) for t in taggings),
        "incomplete": sum(not t.complete for t in taggings),
    }
