"""Owner-scoped node sources; shared catalog candidates must pass every hard check."""

import json
import re
from collections import defaultdict

from sqlalchemy import select

from app.catalog.institutions import domain_of, matches_domain
from app.catalog.matching import match_sources
from app.catalog.taxonomy import tag_records, tag_resource
from app.catalog.verification import is_current, latest_results
from app.llm.embeddings import get_embedding_encoder
from app.roadmap import decode_covers
from app.search.service import canonical_url
from app.vetting.policy import default_policy

from .catalog_models import (
    CatalogCourse,
    CatalogEmbedding,
    Institution,
    NodeMaterial,
    NodeSourceStatus,
    NodeSubject,
    ResourceSubject,
    ResourceVerification,
)
from .models import (
    LearningOutcome,
    NodeResource,
    Resource,
    RoadmapNode,
    Source,
    Syllabus,
)


def verified_resources(db, now):
    """Bulk read of what learners may see (``verification.is_current``).

    Read paths do not mutate the catalog.
    """
    checks = latest_results(
        db.execute(
            select(
                ResourceVerification.resource_id,
                ResourceVerification.check_name,
                ResourceVerification.result,
                ResourceVerification.checked_at,
            ).order_by(
                ResourceVerification.checked_at.desc(), ResourceVerification.id.desc()
            )
        )
    )
    tags = defaultdict(set)
    for row in db.scalars(
        select(ResourceSubject).where(ResourceSubject.confidence >= 0.6)
    ):
        tags[row.resource_id].add(row.subject_id)
    institutions = list(db.scalars(select(Institution)))
    vectors = {
        r.id: (json.loads(r.vector), r.model)
        for r in db.scalars(
            select(CatalogEmbedding).where(
                CatalogEmbedding.kind == "resource",
            )
        )
    }
    rows = []
    for resource, course in db.execute(
        select(Resource, CatalogCourse)
        .outerjoin(CatalogCourse, Resource.catalog_course_id == CatalogCourse.id)
        .where(Resource.verification_status == "verified", Resource.failed_checks < 2)
    ):
        if (
            not is_current(checks.get(resource.id, {}), now)
            or not resource.license
            or not resource.content_hash
            or not resource.canonical_url
            or resource.http_status not in {None, 200}
        ):
            continue
        if default_policy().tier(
            resource.url
        ).value == 0 or resource.canonical_url != canonical_url(resource.url):
            continue
        matching = [
            org for org in institutions if matches_domain(resource.url, org.domain)
        ]
        institution = min(matching, key=lambda org: org.tier) if matching else None
        tier = min(
            [org.tier for org in matching] + [default_policy().tier(resource.url).value]
        )
        rows.append(
            {
                "id": resource.id,
                "kind": "catalog" if resource.catalog_course_id else "web",
                "title": resource.title,
                "url": resource.canonical_url,
                "provider": resource.provider,
                "institution": institution.name if institution else None,
                "license": resource.license,
                "format": resource.format or resource.kind,
                "duration_min": resource.duration_min,
                "verification_status": "verified",
                "lang": resource.lang,
                "level": course.level if course else "undergrad",
                "domain": domain_of(resource.url),
                "tier": tier,
                "subjects": tags[resource.id],
                "is_free": resource.is_free,
                "vector": vectors.get(resource.id, (None, None))[0],
                "vector_model": vectors.get(resource.id, (None, None))[1],
            }
        )
    return rows


def node_sources(db, nodes, roadmap, course, now, *, limit=5):
    """One bulk context for a full roadmap, avoiding a query per node (#102)."""
    identifiers = [n.id for n in nodes]
    node_vectors = {
        r.id: (json.loads(r.vector), r.model)
        for r in db.scalars(
            select(CatalogEmbedding).where(
                CatalogEmbedding.kind == "node",
                CatalogEmbedding.id.in_(identifiers),
            )
        )
    }
    tags = defaultdict(set)
    for row in db.scalars(
        select(NodeSubject).where(
            NodeSubject.node_id.in_(identifiers), NodeSubject.confidence >= 0.6
        )
    ):
        tags[row.node_id].add(row.subject_id)
    materials = defaultdict(dict)  # node -> file name -> one item for all its pages
    covered_subjects = defaultdict(set)
    for attachment, source in db.execute(
        select(NodeMaterial, Source)
        .join(Source, NodeMaterial.source_id == Source.id)
        .where(
            NodeMaterial.node_id.in_(identifiers),
            Source.course_id == course.id,
            NodeMaterial.confidence >= 0.6,
        )
        .order_by(Source.file_name, Source.page)
    ):
        item = materials[attachment.node_id].setdefault(
            source.file_name,
            {
                "kind": "user_material",
                "id": source.id,
                "title": source.file_name,
                "source_id": source.id,
                "pages": [],
                "url": None,
                "provider": "user",
                "institution": None,
                "license": "private",
                "format": "document",
                "duration_min": None,
                "verification_status": "private",
                "score": 1.0,
                "reason": "Tài liệu của bạn",
            },
        )
        item["pages"].append(source.page)
        covered_subjects[attachment.node_id].update(
            t.subject_id
            for t in tag_resource({"title": source.text[:12000]})
            if t.confidence >= 0.9
        )
    syllabus = db.scalars(
        select(Syllabus)
        .where(Syllabus.course_id == course.id)
        .order_by(Syllabus.created_at.desc())
        .limit(1)
    ).first()
    outcomes = (
        list(
            db.scalars(
                select(LearningOutcome.description).where(
                    LearningOutcome.syllabus_id == syllabus.id
                )
            )
        )
        if syllabus
        else []
    )
    references = (
        re.search(
            r"(?ims)^\s*(?:textbooks|references|giáo trình|tài liệu tham khảo)\s*[:\n](.*)",
            syllabus.raw_text,
        )
        if syllabus
        else None
    )
    textbooks = references.group(1).splitlines() if references else []
    rejected = defaultdict(set)
    for row in db.scalars(
        select(NodeResource).where(
            NodeResource.node_id.in_(identifiers), NodeResource.status == "replaced"
        )
    ):
        rejected[row.node_id].add(row.resource_id)
    catalog = verified_resources(db, now)
    result = {}
    for node in nodes:
        # The learner's own files come first (spec 12.1), one item per file.
        private = list(materials[node.id].values())[:limit]
        context = {
            "title": node.title,
            "vector": node_vectors.get(node.id, (None, None))[0],
            "vector_model": node_vectors.get(node.id, (None, None))[1],
            "subjects": tags[node.id],
            "language": course.language,
            "level": "undergrad" if course.level == "university" else course.level,
            "outcomes": outcomes,
            "textbooks": textbooks,
        }
        remaining = [
            r
            for r in catalog
            if r["id"] not in rejected[node.id]
            and not set(r["subjects"]).issubset(covered_subjects[node.id])
        ]
        # A node with private material still gets up to 3 catalog sources for the
        # subjects that material does not cover.
        ranked = match_sources(context, remaining, limit=min(3, limit) if private else limit)
        public = [
            {
                k: r.get(k)
                for k in (
                    "kind",
                    "id",
                    "title",
                    "url",
                    "provider",
                    "institution",
                    "license",
                    "format",
                    "duration_min",
                    "verification_status",
                    "score",
                    "reason",
                )
            }
            for r in ranked
        ]
        sources = private + public
        result[node.id] = {
            "node_id": node.id,
            "status": "ready" if len(sources) >= 2 else "insufficient",
            "source_count": len(sources),
            "user_material_count": len(private),
            "sources": sources,
        }
    return result


def refresh_node_sources(db, nodes, roadmap, course, now):
    """Write selections only from explicit generation/search jobs, never from GET."""
    latest = db.scalar(
        select(Syllabus.id)
        .where(Syllabus.course_id == course.id)
        .order_by(Syllabus.created_at.desc())
        .limit(1)
    )
    outcomes = (
        list(
            db.scalars(
                select(LearningOutcome.description).where(
                    LearningOutcome.syllabus_id == latest
                )
            )
        )
        if latest
        else []
    )
    titles = dict(
        db.execute(
            select(RoadmapNode.id, RoadmapNode.title).where(
                RoadmapNode.roadmap_id == roadmap.id
            )
        ).all()
    )
    tag_records(
        db,
        "node",
        [
            {
                "id": node.id,
                "title": node.title,
                "course": course.title,
                "outcomes": outcomes,
                "covers": [
                    titles[i] for i in decode_covers(node.covers) if i in titles
                ],
            }
            for node in nodes
        ],
        embedding=get_embedding_encoder(),
    )
    result = node_sources(db, nodes, roadmap, course, now)
    for node_id, value in result.items():
        signal = db.get(NodeSourceStatus, node_id)
        if signal is None:
            db.add(
                NodeSourceStatus(
                    node_id=node_id, status=value["status"], updated_at=now
                )
            )
        else:
            signal.status, signal.updated_at = value["status"], now
        selected = {
            r["id"]: r for r in value["sources"] if r["kind"] != "user_material"
        }
        for resource_id, resource in selected.items():
            link = db.get(NodeResource, (node_id, resource_id))
            if link is None:
                db.add(
                    NodeResource(
                        node_id=node_id,
                        resource_id=resource_id,
                        relevance_score=resource["score"],
                    )
                )
            else:
                link.status = "shown"
                link.relevance_score = resource["score"]
        for link in db.scalars(
            select(NodeResource).where(
                NodeResource.node_id == node_id, NodeResource.status == "shown"
            )
        ):
            if link.resource_id not in selected:
                link.status = "removed"
    return result
