"""Owner-scoped node sources; shared catalog candidates must pass every hard check.

Nodes left ``insufficient`` are the catalog's gaps (#105): ``rematch_sources``
selects for them again once new sources are verified.
"""

import json
import threading
from collections import OrderedDict, defaultdict
from functools import lru_cache

import numpy as np
from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased

from app.catalog.institutions import domain_of, parent_domains
from app.catalog.matching import CatalogIndex
from app.catalog.taxonomy import tag_records
from app.catalog.verification import LABEL_CONFIDENCE, is_current, latest_results
from app.llm.embeddings import get_embedding_encoder
from app.roadmap import decode_covers
from app.search.service import canonical_url
from app.syllabus.anchors import textbook_lines
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
    SourceSubject,
)
from .jobs import handler
from .models import (
    Course,
    LearningOutcome,
    NodeResource,
    Resource,
    Roadmap,
    RoadmapNode,
    Source,
    Syllabus,
)

COVERED = 0.9  # a page teaches a subject this surely, so no catalog source repeats it
ENOUGH_CATALOG = 3  # verified sources a node needs without the learner's own material
REMATCH = "rematch_sources"


VECTOR_CACHE = 4096
_vectors: OrderedDict[tuple[str, str, str, str], np.ndarray] = OrderedDict()
_vectors_lock = threading.Lock()


def _decode_vector(row: CatalogEmbedding) -> np.ndarray:
    """A stored embedding as a read-only array, decoded once per worker.

    The key is the row and the sha256 of the text it embeds, never the JSON itself:
    a 3072-float vector is ~60 KB of text, which as a key would dwarf the array.
    shortcut: up to VECTOR_CACHE arrays (~24 KB each at 3072 floats, ~100 MB) per
    worker; move vectors into pgvector before the catalog outgrows that.
    """
    key = (row.id, row.kind, row.model, row.content_hash)
    with _vectors_lock:
        vector = _vectors.get(key)
        if vector is not None:
            _vectors.move_to_end(key)
            return vector
    vector = np.asarray(json.loads(row.vector))
    vector.setflags(write=False)
    with _vectors_lock:
        _vectors[key] = vector
        if len(_vectors) > VECTOR_CACHE:
            _vectors.popitem(last=False)
    return vector


@lru_cache(maxsize=8192)
def _canon_url(url: str) -> str:
    return canonical_url(url)


@lru_cache(maxsize=8192)
def _policy_tier(policy, url: str) -> int:
    return policy.tier(url).value


def _verified_resource_filter():
    return (Resource.verification_status == "verified", Resource.failed_checks < 2)


def _load_verified_checks(db, resource_ids=None):
    stmt = (
        select(
            ResourceVerification.resource_id,
            ResourceVerification.check_name,
            ResourceVerification.result,
            ResourceVerification.checked_at,
        )
        .join(Resource, Resource.id == ResourceVerification.resource_id)
        .where(*_verified_resource_filter())
        .order_by(ResourceVerification.checked_at.desc(), ResourceVerification.id.desc())
    )
    if resource_ids is not None:
        stmt = stmt.where(Resource.id.in_(resource_ids))
    return latest_results(db.execute(stmt))


def _passes_read_gate(resource: Resource, checks, now, policy) -> tuple[bool, int]:
    if (
        not is_current(checks.get(resource.id, {}), now)
        or not resource.license
        or not resource.content_hash
        or not resource.canonical_url
        or resource.http_status not in {None, 200}
    ):
        return False, 0
    policy_tier = _policy_tier(policy, resource.url)
    if policy_tier == 0 or resource.canonical_url != _canon_url(resource.url):
        return False, policy_tier
    return True, policy_tier


def verified_resource_map(db, now, resource_ids) -> dict[str, str]:
    """Scoped ``resource_id -> canonical_url`` for already-identified resources.

    Applies the exact same verification and policy checks as :func:`verified_resources`
    without reading catalog-wide embeddings, tags or institutions (#102, #168).
    """
    ids = list(dict.fromkeys(i for i in resource_ids if i))
    if not ids:
        return {}
    policy = default_policy()
    checks = _load_verified_checks(db, ids)
    rows = db.scalars(
        select(Resource).where(Resource.id.in_(ids), *_verified_resource_filter())
    )
    return {
        r.id: r.canonical_url
        for r in rows
        if _passes_read_gate(r, checks, now, policy)[0]
    }


def verified_resources(db, now):
    """Bulk read of what learners may see (``verification.is_current``).

    Read paths do not mutate the catalog.
    """
    policy = default_policy()
    verified_filter = _verified_resource_filter()
    checks = _load_verified_checks(db)
    tags = defaultdict(set)
    for row in db.scalars(
        select(ResourceSubject)
        .join(Resource, Resource.id == ResourceSubject.resource_id)
        .where(ResourceSubject.confidence >= 0.6, *verified_filter)
    ):
        tags[row.resource_id].add(row.subject_id)
    institutions = {}  # domain -> its best-tier institution
    for org in db.scalars(select(Institution).order_by(Institution.tier, Institution.ror_id)):
        institutions.setdefault(domain_of(org.domain), org)
    vectors = {  # decoded once per worker (_decode_vector), not once per request
        r.id: (_decode_vector(r), r.model)
        for r in db.scalars(
            select(CatalogEmbedding)
            .join(Resource, Resource.id == CatalogEmbedding.id)
            .where(CatalogEmbedding.kind == "resource", *verified_filter)
        )
    }
    rows = []
    for resource, course in db.execute(
        select(Resource, CatalogCourse)
        .outerjoin(CatalogCourse, Resource.catalog_course_id == CatalogCourse.id)
        .where(*verified_filter)
    ):
        ok, policy_tier = _passes_read_gate(resource, checks, now, policy)
        if not ok:
            continue
        matching = [
            institutions[domain]
            for domain in parent_domains(resource.url)
            if domain in institutions
        ]
        institution = min(matching, key=lambda org: org.tier) if matching else None
        tier = min([org.tier for org in matching] + [policy_tier])
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


def node_sources(db, nodes, roadmap, course, now, *, limit=5, catalog=None):
    """One bulk context for a full roadmap, avoiding a query per node (#102).

    ``catalog`` is ``verified_resources(db, now)``, passed by callers that match
    several roadmaps so the catalog is read once.
    """
    if not nodes:
        return {}
    identifiers = [n.id for n in nodes]
    node_vectors = {
        r.id: (_decode_vector(r), r.model)
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
    attached = (
        NodeMaterial.node_id.in_(identifiers),
        Source.course_id == course.id,
        NodeMaterial.confidence >= 0.6,
    )
    materials = defaultdict(dict)  # node -> file name -> one item for all its pages
    for node_id, source_id, file_name, page in db.execute(
        # Page text stays in the database: only the citation is needed here.
        select(NodeMaterial.node_id, Source.id, Source.file_name, Source.page)
        .join(Source, NodeMaterial.source_id == Source.id)
        .where(*attached)
        .order_by(Source.file_name, Source.page)
    ):
        item = materials[node_id].setdefault(
            file_name,
            {
                "kind": "user_material",
                "id": source_id,
                "title": file_name,
                "source_id": source_id,
                "pages": [],
                "url": None,
                "provider": "user",
                "institution": None,
                "license": "private",
                "format": "document",
                "duration_min": None,
                "verification_status": "private",
                "score": 1.0,
                "reason": "Your material",
            },
        )
        item["pages"].append(page)
    covered_subjects = defaultdict(set)  # what the learner's own pages already teach
    for node_id, subject_id in db.execute(
        select(NodeMaterial.node_id, SourceSubject.subject_id)
        .join(Source, NodeMaterial.source_id == Source.id)
        .join(SourceSubject, SourceSubject.source_id == Source.id)
        .where(*attached, SourceSubject.confidence >= COVERED)
    ):
        covered_subjects[node_id].add(subject_id)
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
    textbooks = textbook_lines(syllabus.raw_text) if syllabus else []
    rejected = defaultdict(set)
    for row in db.scalars(
        select(NodeResource).where(
            NodeResource.node_id.in_(identifiers), NodeResource.status == "replaced"
        )
    ):
        rejected[row.node_id].add(row.resource_id)
    catalog = verified_resources(db, now) if catalog is None else catalog
    index = CatalogIndex(catalog)
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
        taught = covered_subjects[node.id]  # by the learner's own pages
        exclude = rejected[node.id] | {
            r["id"] for r in catalog if taught and taught.issuperset(r["subjects"])
        }
        # A node with private material still gets up to 3 catalog sources for the
        # subjects that material does not cover, within ``limit`` items in all.
        room = min(3, limit - len(private)) if private else limit
        ranked = index.match(context, limit=room, exclude=exclude)
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
        covered = bool(private) or len(public) >= ENOUGH_CATALOG
        result[node.id] = {
            "node_id": node.id,
            # Fewer sources stay visible, but the node is a gap for #105 to fill.
            "status": "ready" if covered else "insufficient",
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
    return save_node_sources(db, nodes, roadmap, course, now)


def save_node_sources(db, nodes, roadmap, course, now, *, catalog=None):
    """Select sources for already-tagged nodes and record each node's status."""
    result = node_sources(db, nodes, roadmap, course, now, catalog=catalog)
    if not result:
        return result

    node_ids = list(result.keys())
    statuses_by_node = {
        row.node_id: row
        for row in db.scalars(
            select(NodeSourceStatus).where(NodeSourceStatus.node_id.in_(node_ids))
        )
    }
    existing_links = list(
        db.scalars(select(NodeResource).where(NodeResource.node_id.in_(node_ids)))
    )
    links_by_pair = {(link.node_id, link.resource_id): link for link in existing_links}
    shown_by_node: dict[str, list[NodeResource]] = defaultdict(list)
    for link in existing_links:
        if link.status == "shown":
            shown_by_node[link.node_id].append(link)

    new_rows: list[object] = []
    for node_id, value in result.items():
        signal = statuses_by_node.get(node_id)
        if signal is None:
            new_rows.append(
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
            link = links_by_pair.get((node_id, resource_id))
            if link is None:
                new_rows.append(
                    NodeResource(
                        node_id=node_id,
                        resource_id=resource_id,
                        relevance_score=resource["score"],
                    )
                )
            else:
                link.status = "shown"
                link.relevance_score = resource["score"]
        for link in shown_by_node.get(node_id, ()):
            if link.resource_id not in selected:
                link.status = "removed"
    if new_rows:
        db.add_all(new_rows)
    return result


# --- gaps (#105) ---------------------------------------------------------------------


def current_nodes():
    """Nodes of each course's newest roadmap, the one its learner follows."""
    newer = aliased(Roadmap)
    current = select(Roadmap.id).where(
        ~exists().where(newer.course_id == Roadmap.course_id, newer.created_at > Roadmap.created_at)
    )
    return select(RoadmapNode.id).where(RoadmapNode.roadmap_id.in_(current))


def insufficient_nodes():
    """Ids of current nodes whose last selection found fewer than two sources."""
    return select(NodeSourceStatus.node_id).where(
        NodeSourceStatus.status == "insufficient",
        NodeSourceStatus.node_id.in_(current_nodes()),
    )


def gap_subjects(db) -> dict[str, int]:
    """Subject label -> insufficient nodes carrying it, the labels to ingest for."""
    return dict(
        db.execute(
            select(NodeSubject.subject_id, func.count())
            .where(
                NodeSubject.node_id.in_(insufficient_nodes()),
                NodeSubject.confidence >= LABEL_CONFIDENCE,
            )
            .group_by(NodeSubject.subject_id)
            .order_by(NodeSubject.subject_id)
        ).all()
    )


def rematch_insufficient(db, now) -> dict:
    """Select again for insufficient nodes, e.g. after new sources were verified.

    Labels stay as they are (no embedding calls) and the catalog is read once for
    every roadmap, so the cost grows with the catalog, not with the learners.
    """
    # shortcut: one job re-matches every insufficient node; chain batches of roadmaps
    # once that nears the 10-minute job lease (thousands of roadmaps with gaps).
    nodes = list(db.scalars(select(RoadmapNode).where(RoadmapNode.id.in_(insufficient_nodes()))))
    if not nodes:
        return {"insufficient_before": 0, "insufficient_after": 0}
    by_roadmap = defaultdict(list)
    for node in nodes:
        by_roadmap[node.roadmap_id].append(node)
    roadmaps_by_id = {
        r.id: r
        for r in db.scalars(select(Roadmap).where(Roadmap.id.in_(by_roadmap.keys())))
    }
    course_ids = {r.course_id for r in roadmaps_by_id.values()}
    courses_by_id = (
        {
            c.id: c
            for c in db.scalars(select(Course).where(Course.id.in_(course_ids)))
        }
        if course_ids
        else {}
    )
    catalog = verified_resources(db, now)
    for roadmap_id, group in by_roadmap.items():
        roadmap = roadmaps_by_id.get(roadmap_id)
        if roadmap is None:
            continue
        save_node_sources(
            db,
            group,
            roadmap,
            courses_by_id.get(roadmap.course_id),
            now,
            catalog=catalog,
        )
    db.flush()
    after = db.scalar(select(func.count()).select_from(insufficient_nodes().subquery()))
    return {"insufficient_before": len(nodes), "insufficient_after": after}


@handler(REMATCH)
def rematch_sources(db, payload, now) -> dict:
    return rematch_insufficient(db, now)
