"""Find the numbered exercises a concept's own pages already print; never write one (#115)."""

import json
from uuid import uuid4

from sqlalchemy import bindparam, text

from app.catalog.exercises import exact, extract_numbered, from_offsets
from app.concepts.normalize import pages_in
from app.retrieval import retrieve_top_k

TOP_K = 3
MAX_ITEMS = 5


def pick_pages(concept: dict, sources: list[dict]) -> list[dict]:
    """Top-3 BM25 pages for the concept, ranked among the pages it cites in their own file
    (``source_refs``, see pages_in) when it has any, else among all pages; its other cited
    pages fill the rest."""
    own = [
        {"id": str(s["id"]), "page": s["page"], "text": s["text"]}
        for s in sources
        if s["page"] in pages_in(concept, s.get("file_name"))
    ]
    hits = retrieve_top_k(
        f"{concept['title']} {concept['summary']}", own or sources, top_k=TOP_K
    )
    picked = [{"id": h.source_id, "page": h.page, "text": h.text} for h in hits]
    ids = {p["id"] for p in picked}
    return (picked + [p for p in own if p["id"] not in ids])[:TOP_K]


def parse_items(answer, sources):
    """Accept offset proposals only; a collection of source IDs is not evidence."""
    data = json.loads(answer)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise TypeError("expected offset items")
    if not isinstance(sources, dict):
        return []
    result = []
    for proposal in data["items"]:
        if not isinstance(proposal, dict) or set(proposal) - {
            "source_id",
            "start",
            "end",
        }:
            continue
        source = sources.get(proposal.get("source_id"))
        if source is None:
            continue
        spans = [{k: proposal[k] for k in ("start", "end") if k in proposal}]
        result.extend(
            {**item, "source_id": proposal["source_id"]}
            for item in from_offsets(source, spans)
        )
    return result[:MAX_ITEMS]


def find_items(concept, sources):
    """Quoted exercises from the concept's best pages, at most MAX_ITEMS."""
    return [
        {**item, "source_id": page["id"]}
        for page in pick_pages(concept, sources)
        for item in extract_numbered(page["text"])
    ][:MAX_ITEMS]


def save_items(db, concept_id, items):
    """FSRS compatibility rows always point at a verified, owner-scoped exercise."""
    from app.catalog.exercises import store_private

    course = db.execute(
        text(
            "SELECT c.course_id, cr.owner_id FROM concepts c "
            "JOIN courses cr ON cr.id = c.course_id WHERE c.id = :id"
        ),
        {"id": concept_id},
    ).first()
    if course is None or course.owner_id is None or not items:
        return []
    # items come from find_items, at most MAX_ITEMS, so one IN query needs no chunking.
    sources = {
        row["id"]: row
        for row in db.execute(
            text(
                "SELECT id,course_id,text,page FROM sources WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": list({item.get("source_id") for item in items})},
        ).mappings()
    }
    known = set(
        db.scalars(
            text("SELECT exercise_id FROM items WHERE concept_id=:c"), {"c": concept_id}
        )
    )
    exercises = {}  # source id -> quote hash -> exercise; one store_private per page
    saved = []
    for item in items:
        source = sources.get(item.get("source_id"))
        if (
            source is None
            or source["course_id"] != course.course_id
            or not exact(item, source["text"])
        ):
            continue
        if source["id"] not in exercises:
            exercises[source["id"]] = {
                e["quote_hash"]: e for e in store_private(db, source, course.owner_id)
            }
        exercise = exercises[source["id"]].get(item["quote_hash"])
        if exercise is None or exercise["id"] in known:
            continue
        known.add(exercise["id"])
        saved.append(
            {
                **item,
                "id": str(uuid4()),
                "concept_id": concept_id,
                "exercise_id": exercise["id"],
                "choices": json.dumps(item.get("choices") or [], ensure_ascii=False),
                "answer": item.get("answer") or "",
                "rubric": None,
            }
        )
    if saved:
        db.execute(
            text(
                "INSERT INTO items (id,concept_id,exercise_id,source_id,type,prompt,choices,answer,rubric) "
                "VALUES (:id,:concept_id,:exercise_id,:source_id,:type,:prompt,:choices,:answer,:rubric)"
            ),
            saved,
        )
    return saved
