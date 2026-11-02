"""Owner-scoped concept proposals and cited question drafts."""
import json
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.ai_data import StrictModel
from app.concepts.extract import extract_concepts, same_concept
from app.items.generate import generate_items
from app.llm import get_client

from .auth import Database, User, fail, owned_course

router = APIRouter(prefix="/api/v1")


def client_for(request):
    if request.app.state.llm_client is not None:
        return request.app.state.llm_client
    try:
        return get_client()
    except (RuntimeError, ValueError):
        fail(503, "llm_not_configured", "Configure the LLM provider before generating content.")


def source_rows(database, course_id):
    return [dict(row) for row in database.execute(text(
        "SELECT * FROM sources WHERE course_id=:id ORDER BY file_name,page"
    ), {"id": course_id}).mappings()]


def concept_json(row):
    return {**dict(row), "source_pages": json.loads(row["source_pages"] or "[]"),
            "source_ids": json.loads(row["source_ids"]),
            "confirmed": bool(row["confirmed"])}


def owned_concept(database, concept_id, user):
    row = database.execute(text(
        "SELECT concepts.* FROM concepts JOIN courses ON courses.id=concepts.course_id "
        "WHERE concepts.id=:id AND courses.owner_id=:owner"
    ), {"id": concept_id, "owner": user}).mappings().first()
    if row is None:
        fail(404, "not_found", "Concept not found.")
    return concept_json(row)


@router.get("/courses/{course_id}/concepts")
def list_concepts(course_id: str, user: User, database: Database):
    owned_course(database, course_id, user)
    rows = database.execute(text("SELECT * FROM concepts WHERE course_id=:id ORDER BY slug"),
                            {"id": course_id}).mappings()
    return {"concepts": [concept_json(row) for row in rows]}


@router.post("/courses/{course_id}/concepts:propose")
def propose_concepts(course_id: str, request: Request,
                     user: User, database: Database):
    owned_course(database, course_id, user)
    sources = source_rows(database, course_id)
    if not any(row["text"].strip() for row in sources):
        return {"concepts": [], "prereqs": [], "warnings": ["missing_knowledge"]}
    client = client_for(request)
    try:
        proposals = extract_concepts(sources, client)
    except ValueError:
        fail(502, "invalid_llm_response", "The model returned invalid concept data; nothing was saved.")
    except Exception:  # noqa: BLE001 - provider errors must not expose source text or credentials
        # Keep provider diagnostics (which may contain request text or credentials) out of responses.
        fail(502, "llm_unavailable", "The model request failed; try again later.")
    existing = list_concepts(course_id, user, database)["concepts"]
    result = []
    try:
        for proposal in proposals:
            match = next((row for row in existing if same_concept(row, proposal)), None)
            if match is not None:
                if not match["confirmed"]:
                    match["source_pages"] = sorted(set(match["source_pages"]) | set(proposal["source_pages"]))
                    match["source_ids"] = sorted(set(match["source_ids"]) | set(proposal["source_ids"]))
                    database.execute(text("UPDATE concepts SET source_pages=:pages,source_ids=:sources WHERE id=:id"),
                                     {"pages": json.dumps(match["source_pages"]),
                                      "sources": json.dumps(match["source_ids"]), "id": match["id"]})
                result.append(match)
                continue
            row = {"id": "k_" + uuid4().hex, "course_id": course_id, **proposal, "confirmed": False}
            database.execute(text(
                "INSERT INTO concepts (id,course_id,slug,title,summary,bloom_level,source_pages,source_ids) "
                "VALUES (:id,:course_id,:slug,:title,:summary,:bloom_level,:source_pages,:source_ids)"
            ), {**row, "source_pages": json.dumps(row["source_pages"]), "source_ids": json.dumps(row["source_ids"])})
            existing.append(row)
            result.append(row)
        database.commit()
    except IntegrityError:
        database.rollback()
        fail(409, "concept_conflict", "Concepts changed concurrently; reload and retry.")
    return {"concepts": result, "prereqs": []}


class Confirmation(StrictModel):
    confirmed: bool


@router.patch("/concepts/{concept_id}")
def confirm_concept(concept_id: str, data: Confirmation,
                    user: User, database: Database):
    row = owned_concept(database, concept_id, user)
    database.execute(text("UPDATE concepts SET confirmed=:confirmed WHERE id=:id"),
                     {"confirmed": int(data.confirmed), "id": concept_id})
    database.commit()
    return {**row, "confirmed": data.confirmed}


@router.get("/concepts/{concept_id}/items")
def list_items(concept_id: str, user: User, database: Database):
    owned_concept(database, concept_id, user)
    rows = database.execute(text(
        "SELECT items.*,sources.file_name,sources.page FROM items JOIN sources ON sources.id=items.source_id "
        "WHERE concept_id=:id ORDER BY items.id"
    ), {"id": concept_id}).mappings()
    return {"items": [{**dict(row), "choices": json.loads(row["choices"]) if row["choices"] else None,
                       "rubric": json.loads(row["rubric"]) if row["rubric"] else None,
                       "source": {"source_id": row["source_id"], "file_name": row["file_name"], "page": row["page"]}}
                      for row in rows]}


@router.post("/concepts/{concept_id}/items:generate")
def create_items(concept_id: str, request: Request,
                 user: User, database: Database):
    concept = owned_concept(database, concept_id, user)
    if not concept["confirmed"]:
        fail(409, "concept_unconfirmed", "Confirm this concept before generating questions.")
    # Week-one fallback specified in AI.md while #11 BM25 is owned by Thang.
    sources = [row for row in source_rows(database, concept["course_id"])
               if row["id"] in concept["source_ids"] and row["text"].strip()][:3]
    if not sources:
        return {"items": [], "warnings": ["missing_knowledge"]}
    client = client_for(request)
    try:
        items = generate_items(concept, sources, client)
    except ValueError:
        fail(502, "invalid_llm_response", "The model returned invalid question data; nothing was saved.")
    except Exception:  # noqa: BLE001 - normalize third-party provider failures without leaking data
        fail(502, "llm_unavailable", "The model request failed; try again later.")
    if not items:
        return {"items": [], "warnings": ["insufficient_cited_items"]}
    ids = []
    for item in items:
        item_id = "i_" + uuid4().hex
        ids.append(item_id)
        database.execute(text(
            "INSERT INTO items (id,concept_id,source_id,type,prompt,choices,answer,rubric) "
            "VALUES (:id,:concept_id,:source_id,:type,:prompt,:choices,:answer,:rubric)"
        ), {**item, "id": item_id, "concept_id": concept_id,
            "choices": json.dumps(item["choices"]) if item["choices"] is not None else None,
            "rubric": json.dumps(item["rubric"], ensure_ascii=False) if item["rubric"] is not None else None})
    database.commit()
    return {"items": [row for row in list_items(concept_id, user, database)["items"] if row["id"] in ids]}
