"""Compatibility entry points: extract existing exercises; never generate prose (#115)."""

import json
from uuid import uuid4

from sqlalchemy import text

from app.catalog.exercises import exact, extract_numbered, from_offsets
from app.retrieval import retrieve_top_k

TOP_K = 3
MAX_ITEMS = 5


def pick_pages(concept: dict, sources: list[dict]) -> list[dict]:
    """Top-3 BM25 pages for the concept, ranked among the pages it cites (``source_pages``)
    when it has any, else among all pages; its other cited pages fill the rest."""
    cited = set(concept.get("source_pages") or [])
    own = [
        {"id": str(s["id"]), "page": s["page"], "text": s["text"]}
        for s in sources
        if s["page"] in cited
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


def generate_items(llm, concept, sources):
    """Deprecated name retained for callers; llm is deliberately never invoked."""
    return [
        {**item, "source_id": page["id"]}
        for page in pick_pages(concept, sources)
        for item in extract_numbered(page["text"])
    ][:MAX_ITEMS]


def save_items(db, concept_id, items):
    """FSRS compatibility rows always point at a verified, owner-scoped exercise."""
    from app.catalog.exercises import store_private

    saved = []
    course_id = db.scalar(
        text("SELECT course_id FROM concepts WHERE id=:id"), {"id": concept_id}
    )
    owner = db.scalar(
        text("SELECT owner_id FROM courses WHERE id=:id"), {"id": course_id}
    )
    if owner is None:
        return []
    for item in items:
        source = (
            db.execute(
                text("SELECT id,course_id,text,page FROM sources WHERE id=:id"),
                {"id": item.get("source_id")},
            )
            .mappings()
            .first()
        )
        if (
            source is None
            or source["course_id"] != course_id
            or not exact(item, source["text"])
        ):
            continue
        exercises = store_private(db, source, owner)
        exercise = next(
            (e for e in exercises if e["quote_hash"] == item["quote_hash"]), None
        )
        if exercise is None:
            continue
        exists = db.execute(
            text("SELECT id FROM items WHERE concept_id=:c AND exercise_id=:e"),
            {"c": concept_id, "e": exercise["id"]},
        ).first()
        if exists:
            continue
        row = {
            **item,
            "id": str(uuid4()),
            "concept_id": concept_id,
            "exercise_id": exercise["id"],
            "choices": json.dumps(item.get("choices") or [], ensure_ascii=False),
            "answer": item.get("answer") or "",
            "rubric": None,
        }
        db.execute(
            text(
                "INSERT INTO items (id,concept_id,exercise_id,source_id,type,prompt,choices,answer,rubric) "
                "VALUES (:id,:concept_id,:exercise_id,:source_id,:type,:prompt,:choices,:answer,:rubric)"
            ),
            row,
        )
        saved.append(row)
    return saved
