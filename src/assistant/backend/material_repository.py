"""A learner's own material on their roadmap (#114): mapping job, review, deletion.

Private by construction: material lives in ``sources`` (per page), ``node_materials``
and owner-scoped ``exercises`` only, never in the shared ``resources`` catalog, and
never goes through public verification (ADR 004). Callers check course ownership.

Mapping runs as a background job ("map_materials") after an upload or a new
roadmap: it may call the LLM once per file, which does not belong in a request.
The job only rewrites "auto" rows, so it is safe to repeat (jobs are at least once)
and never overrides what the learner confirmed or rejected.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, select

from app.llm import get_client
from app.llm.embeddings import get_embedding_encoder
from app.materials import REVIEW, Node, map_pages

from .catalog_models import NodeMaterial
from .exercise_repository import import_private_exercises
from .jobs import enqueue, handler
from .models import Course, Job, Roadmap, RoadmapNode, Source

MAP_JOB = "map_materials"
ATTACHED, REJECTED = 1.0, 0.0  # confidence of the learner's own decisions


def latest_roadmap(db, course_id: str) -> Roadmap | None:
    return db.scalars(
        select(Roadmap)
        .where(Roadmap.course_id == course_id)
        .order_by(Roadmap.created_at.desc())
        .limit(1)
    ).first()


def enqueue_mapping(db, course: Course, now: datetime, *, file_name=None) -> Job | None:
    """Queue a mapping run when there is both material and a roadmap to map it onto."""
    query = select(Source.id).where(Source.course_id == course.id, Source.kind == "material")
    if file_name is not None:
        query = query.where(Source.file_name == file_name)
    if db.scalar(query.limit(1)) is None or latest_roadmap(db, course.id) is None:
        return None
    payload = {"course_id": course.id, "file_name": file_name}
    return enqueue(db, MAP_JOB, payload, now=now, user_id=course.owner_id)


@handler(MAP_JOB)
def map_materials(db, payload: dict, now: datetime) -> dict:
    """Suggest a node for every page of the course's material (or of one file)."""
    course = db.get(Course, payload["course_id"])
    roadmap = latest_roadmap(db, course.id) if course else None
    if roadmap is None:
        return {"status": "nothing_to_map"}
    # Milestones examine topics; material is attached to the topics themselves.
    nodes = [
        Node(node.id, node.title)
        for node in db.scalars(
            select(RoadmapNode)
            .where(RoadmapNode.roadmap_id == roadmap.id, RoadmapNode.type == "topic")
            .order_by(RoadmapNode.week, RoadmapNode.title)
        )
    ]
    query = select(Source).where(Source.course_id == course.id, Source.kind == "material")
    if payload.get("file_name"):
        query = query.where(Source.file_name == payload["file_name"])
    files = defaultdict(list)
    for source in db.scalars(query.order_by(Source.file_name, Source.page)):
        files[source.file_name].append(source)
    llm, embedding = get_client(), get_embedding_encoder()
    counts = {"status": "done", "files": len(files), "attached": 0, "suggested": 0}
    for sources in files.values():
        # Vision notes carry what the text layer misses (diagrams, photos).
        pages = [f"{s.text}\n{s.visual_notes or ''}" for s in sources]
        matches = map_pages(pages, nodes, embedding=embedding, llm=llm)
        for match in _save(db, sources, matches):
            counts["attached" if match.confidence >= REVIEW else "suggested"] += 1
    return counts


def _save(db, sources, matches):
    """Replace the "auto" rows of these pages; pages the learner decided are kept."""
    ids = [source.id for source in sources]
    db.execute(
        delete(NodeMaterial).where(
            NodeMaterial.source_id.in_(ids), NodeMaterial.method == "auto"
        )
    )
    decided = {
        (row.node_id, row.source_id): row.confidence
        for row in db.scalars(select(NodeMaterial).where(NodeMaterial.source_id.in_(ids)))
    }
    confirmed = {source for (_, source), value in decided.items() if value >= REVIEW}
    by_page = {source.page: source for source in sources}
    saved = []
    for match in matches:
        source = by_page[match.page]
        if source.id in confirmed or (match.node_id, source.id) in decided:
            continue
        db.add(
            NodeMaterial(
                node_id=match.node_id,
                source_id=source.id,
                confidence=match.confidence,
                method="auto",
            )
        )
        saved.append(match)
    db.flush()
    return saved


def node_materials(db, node: RoadmapNode) -> list[dict]:
    """Pages attached to or suggested for ``node``, grouped by file; rejected ones left out."""
    rows = db.execute(
        select(NodeMaterial, Source)
        .join(Source, NodeMaterial.source_id == Source.id)
        .where(NodeMaterial.node_id == node.id, NodeMaterial.confidence > REJECTED)
        .order_by(Source.file_name, Source.page)
    ).all()
    files = {}
    for attachment, source in rows:
        status = "attached" if attachment.confidence >= REVIEW else "suggested"
        group = files.setdefault(
            (source.file_name, status),
            {"file_name": source.file_name, "status": status, "pages": []},
        )
        group["pages"].append(
            {
                "source_id": source.id,
                "page": source.page,
                "confidence": attachment.confidence,
                "method": attachment.method,
            }
        )
    return list(files.values())


def decide(db, node: RoadmapNode, source: Source, *, attached: bool, owner_id: str):
    """The learner attaches, confirms or rejects one page for one node."""
    row = db.get(NodeMaterial, (node.id, source.id))
    if row is None:
        row = NodeMaterial(node_id=node.id, source_id=source.id)
        db.add(row)
    row.confidence, row.method = (ATTACHED if attached else REJECTED), "manual"
    if attached:
        # Pages uploaded before exercise import (#115) still yield their exercises.
        import_private_exercises(db, source, owner_id)
    db.flush()
    return row


def delete_material(db, course: Course, file_name: str) -> int:
    """Delete one file's pages; node links and its private exercises cascade (FKs)."""
    result = db.execute(
        delete(Source).where(Source.course_id == course.id, Source.file_name == file_name)
    )
    return result.rowcount
