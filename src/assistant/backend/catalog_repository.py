"""Owner-scoped node sources; shared catalog candidates must pass every hard check."""

import json
import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from app.catalog.institutions import domain_of, matches_domain
from app.catalog.matching import match_sources
from app.catalog.taxonomy import save_tags, tag_node, tag_resource
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
from .models import LearningOutcome, NodeResource, Resource, Source, Syllabus

CHECKS = {"fetch", "domain", "license", "metadata"}


def verified_resources(db, now):
    """Bulk read: latest result of each check wins, not any historic pass.

    This also fails closed if a producer incorrectly sets verification_status
    without four fresh checks. Read paths do not mutate the catalog.
    """
    checks = defaultdict(dict)
    for row in db.scalars(
        select(ResourceVerification).order_by(
            ResourceVerification.checked_at.desc(), ResourceVerification.id.desc()
        )
    ):
        checks[row.resource_id].setdefault(row.check_name, row)
    tags = defaultdict(set)
    for row in db.scalars(
        select(ResourceSubject).where(ResourceSubject.confidence >= 0.6)
    ):
        tags[row.resource_id].add(row.subject_id)
    institutions = list(db.scalars(select(Institution)))
    vectors = {
        r.id: json.loads(r.vector)
        for r in db.scalars(
            select(CatalogEmbedding).where(
                CatalogEmbedding.kind == "resource",
                CatalogEmbedding.model == "sha256-word-bigram-256-v1",
            )
        )
    }
    rows = []
    for resource, course in db.execute(
        select(Resource, CatalogCourse)
        .outerjoin(CatalogCourse, Resource.catalog_course_id == CatalogCourse.id)
        .where(Resource.verification_status == "verified", Resource.failed_checks < 2)
    ):
        verified = checks[resource.id]
        if (
            not CHECKS.issubset(verified)
            or any(
                verified[c].result != "pass"
                or not now - timedelta(days=30) <= verified[c].checked_at <= now
                for c in CHECKS
            )
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
                "vector": vectors.get(resource.id),
            }
        )
    return rows


def node_sources(db, nodes, roadmap, course, now, *, limit=5):
    """One bulk context for a full roadmap, avoiding a query per node (#102)."""
    identifiers = [n.id for n in nodes]
    node_vectors = {
        r.id: json.loads(r.vector)
        for r in db.scalars(
            select(CatalogEmbedding).where(
                CatalogEmbedding.kind == "node",
                CatalogEmbedding.id.in_(identifiers),
                CatalogEmbedding.model == "sha256-word-bigram-256-v1",
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
    materials = defaultdict(list)
    covered_subjects = defaultdict(set)
    for attachment, source in db.execute(
        select(NodeMaterial, Source)
        .join(Source, NodeMaterial.source_id == Source.id)
        .where(
            NodeMaterial.node_id.in_(identifiers),
            Source.course_id == course.id,
            NodeMaterial.confidence >= 0.6,
        )
    ):
        materials[attachment.node_id].append(
            {
                "kind": "user_material",
                "id": source.id,
                "title": source.file_name,
                "source_id": source.id,
                "pages": [source.page],
                "url": None,
                "provider": "user",
                "institution": None,
                "license": "private",
                "format": "document",
                "duration_min": None,
                "verification_status": "private",
                "score": 1.0,
                "reason": "Tài liệu của bạn",
            }
        )
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
            NodeResource.node_id.in_(identifiers), NodeResource.status != "shown"
        )
    ):
        rejected[row.node_id].add(row.resource_id)
    catalog = verified_resources(db, now)
    result = {}
    for node in nodes:
        private = sorted(materials[node.id], key=lambda r: (r["title"], r["pages"]))[
            :limit
        ]
        context = {
            "title": node.title,
            "vector": node_vectors.get(node.id),
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
        ranked = match_sources(
            context, remaining, limit=min(3 if private else 5, limit - len(private))
        )
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
    for node in nodes:
        save_tags(
            db,
            "node",
            node.id,
            tag_node(node, course=course.title, outcomes=outcomes),
            " ".join([node.title, course.title, *outcomes]),
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
            if db.get(NodeResource, (node_id, resource_id)) is None:
                db.add(
                    NodeResource(
                        node_id=node_id,
                        resource_id=resource_id,
                        relevance_score=resource["score"],
                    )
                )
        for link in db.scalars(
            select(NodeResource).where(
                NodeResource.node_id == node_id, NodeResource.status == "shown"
            )
        ):
            if link.resource_id not in selected:
                link.status = "removed"
    return result
