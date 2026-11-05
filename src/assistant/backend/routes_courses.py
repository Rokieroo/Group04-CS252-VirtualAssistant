"""Courses, page-level PDF/DOCX/PPTX/photo/text sources (UC-01, #13, #49, #114), concept proposals (UC-02, #9) and cited items (UC-03, #10)."""

import json
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.concepts.extract import extract_concepts, save_concepts
from app.concepts.visual import read_visuals
from app.ingest import (
    MAX_UPLOAD_BYTES,
    InvalidDocument,
    UnsupportedType,
    as_pdf,
    detect_media_type,
    extract_pages,
    looks_scanned,
)
from app.items.generate import generate_items, save_items
from app.llm import LLMClient, get_client, get_vision_client

from .dependencies import DB, CurrentUser
from .material_repository import delete_material, enqueue_mapping
from .models import Course, Source
from .schemas import (
    ConceptGraphOut,
    CourseCreate,
    CourseOut,
    ItemOut,
    SourceKind,
    SourceOut,
    UploadOut,
)

router = APIRouter(tags=["Courses and sources"])


def owned_course(db, course_id: str, user_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.owner_id != user_id:
        raise HTTPException(404, "Course not found")  # never reveal others' courses
    return course


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(data: CourseCreate, db: DB, user: CurrentUser):
    course = Course(owner_id=user.id, **data.model_dump())
    db.add(course)
    db.commit()
    return course


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: DB, user: CurrentUser):
    return db.scalars(
        select(Course).where(Course.owner_id == user.id).order_by(Course.created_at)
    ).all()


@router.get("/courses/{course_id}/sources", response_model=list[SourceOut])
def list_sources(course_id: str, db: DB, user: CurrentUser):
    owned_course(db, course_id, user.id)
    return db.scalars(
        select(Source)
        .where(Source.course_id == course_id)
        .order_by(Source.file_name, Source.page)
    ).all()


@router.post("/courses/{course_id}/sources", response_model=UploadOut, status_code=201)
def upload_source(
    course_id: str,
    file: UploadFile,
    request: Request,
    db: DB,
    user: CurrentUser,
    vision: Annotated[LLMClient, Depends(get_vision_client)],
    kind: Annotated[SourceKind, Form()] = "material",
):
    """PDF, DOCX, PPTX, JPEG/PNG photo or UTF-8 .txt up to 20 MB; the type comes from name
    and content, not the client. Material is then mapped onto the roadmap in a job."""
    course = owned_course(db, course_id, user.id)
    # Browsers may send a Windows path; keep only the base name.
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not 1 <= len(name) <= 255:
        raise HTTPException(422, "invalid_file_name")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file_too_large")
    try:
        media_type = detect_media_type(name, data)
        pages = extract_pages(data, media_type)
    except UnsupportedType:
        raise HTTPException(415, "unsupported_type") from None
    except InvalidDocument as exc:
        raise HTTPException(400, exc.code) from None
    # PDFs and photos have page images for the vision model to read.
    pdf = as_pdf(data, media_type)
    notes = (
        read_visuals(vision, pdf, len(pages), _previous_notes(db, course_id, name, len(pages)))
        if pdf
        else [""] * len(pages)
    )
    # Re-uploading the same file name replaces its pages.
    db.execute(
        delete(Source).where(Source.course_id == course_id, Source.file_name == name)
    )
    db.add_all(
        Source(course_id=course_id, file_name=name, page=number, text=text,
               visual_notes=note or None, kind=kind)
        for number, (text, note) in enumerate(zip(pages, notes, strict=True), start=1)
    )
    from .exercise_repository import import_private_exercises
    db.flush()
    for source in db.scalars(select(Source).where(Source.course_id == course_id, Source.file_name == name)):
        import_private_exercises(db, source, user.id)
    job = (
        enqueue_mapping(db, course, request.app.state.now(), file_name=name)
        if kind == "material"
        else None
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "upload_in_progress") from None
    return UploadOut(
        file_name=name,
        pages=len(pages),
        kind=kind,
        status="processed",
        warning="scanned_pdf" if pdf and looks_scanned(pages) else None,
        mapping_job_id=job.id if job else None,
    )


@router.delete("/courses/{course_id}/sources/{file_name}", status_code=204)
def delete_source_file(course_id: str, file_name: str, db: DB, user: CurrentUser):
    """Delete an uploaded file: its pages, their node links and the exercises quoted from it."""
    course = owned_course(db, course_id, user.id)
    if not delete_material(db, course, file_name):
        raise HTTPException(404, "File not found")
    db.commit()
    return Response(status_code=204)


def _previous_notes(db, course_id: str, name: str, page_count: int) -> list[str]:
    """A re-upload revises the notes kept from last time; a failed chunk keeps them."""
    previous = [""] * page_count
    for number, note in db.execute(select(Source.page, Source.visual_notes).where(
            Source.course_id == course_id, Source.file_name == name)):
        if number <= page_count:
            previous[number - 1] = note or ""
    return previous


@router.post("/courses/{course_id}/concepts:propose", response_model=ConceptGraphOut)
def propose_concepts(
    course_id: str,
    db: DB,
    user: CurrentUser,
    llm: Annotated[LLMClient, Depends(get_client)],
    file_name: str | None = None,
):
    """Extract concepts from uploaded pages (one file, or every file) and store them unconfirmed."""
    owned_course(db, course_id, user.id)
    query = select(Source.file_name, Source.text, Source.visual_notes).where(
        Source.course_id == course_id)
    if file_name is not None:
        query = query.where(Source.file_name == file_name)
    decks: dict[str, tuple[list[str], list[str]]] = {}
    for name, page_text, note in db.execute(query.order_by(Source.file_name, Source.page)):
        pages, notes = decks.setdefault(name, ([], []))
        pages.append(page_text)
        notes.append(note or "")
    if not decks:
        raise HTTPException(404, "no_sources")
    # A re-run revises what was proposed before rather than starting over.
    previous = [{**row, "source_pages": json.loads(row["source_pages"] or "[]")}
                for row in db.execute(text(
                    "SELECT slug, title, summary, source_pages FROM concepts "
                    "WHERE course_id = :course_id"), {"course_id": course_id}).mappings()]
    for pages, notes in decks.values():
        concepts = extract_concepts(llm, pages, notes, previous)
        # shortcut: a deck with text but no concepts means every LLM call failed (quota,
        # network, bad JSON); report it rather than look like an empty deck.
        if not concepts and (any(pages) or any(notes)):
            raise HTTPException(503, "concepts_unavailable")
        save_concepts(db, course_id, concepts)
    try:
        db.commit()
    except IntegrityError:  # a concurrent proposal inserted the same slug
        db.rollback()
        raise HTTPException(409, "proposal_in_progress") from None
    rows = db.execute(text(
        "SELECT id, slug, title, summary, bloom_level, source_pages, confirmed FROM concepts "
        "WHERE course_id = :course_id"), {"course_id": course_id}).mappings()
    concepts = [{**row, "source_pages": json.loads(row["source_pages"] or "[]")} for row in rows]
    concepts.sort(key=lambda c: (c["source_pages"] or [0])[0])
    return {"concepts": concepts, "prereqs": []}


def course_concept(db, course_id: str, concept_id: str) -> dict:
    row = db.execute(text(
        "SELECT id, title, summary, source_pages FROM concepts "
        "WHERE id = :id AND course_id = :course_id"),
        {"id": concept_id, "course_id": course_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Concept not found")
    return {**row, "source_pages": json.loads(row["source_pages"] or "[]")}


def concept_items(db, concept_id: str) -> list[dict]:
    import hashlib

    from app.catalog.exercises import exact, quote_hash
    rows = db.execute(text(
        "SELECT i.id, i.type, i.prompt, i.choices, i.answer, i.rubric, i.source_id, i.status, "
        "s.page, s.file_name, s.text AS source_text, e.quote_hash, e.source_hash "
        "FROM items i JOIN sources s ON s.id = i.source_id "
        "JOIN exercises e ON e.id = i.exercise_id AND e.source_id = i.source_id "
        "JOIN concepts c ON c.id = i.concept_id JOIN courses co ON co.id = c.course_id "
        "WHERE i.concept_id = :id AND e.verification_status = 'verified' AND i.status <> 'rejected' "
        "AND s.course_id=c.course_id AND e.owner_id=co.owner_id "
        "ORDER BY s.file_name, s.page, i.type, i.id"),
        {"id": concept_id}).mappings()
    result = []
    for row in rows:
        item = {**row, "choices": json.loads(row["choices"] or "[]"),
                "rubric": json.loads(row["rubric"] or "[]")}
        if (exact(item, row["source_text"]) and
                hashlib.sha256(row["source_text"].encode()).hexdigest() == row["source_hash"] and
                quote_hash(item["prompt"], item["choices"], item["answer"]) == row["quote_hash"]):
            result.append(item)
    return result


@router.get("/courses/{course_id}/concepts/{concept_id}/items", response_model=list[ItemOut])
def list_items(course_id: str, concept_id: str, db: DB, user: CurrentUser):
    owned_course(db, course_id, user.id)
    course_concept(db, course_id, concept_id)
    return concept_items(db, concept_id)


@router.post("/courses/{course_id}/concepts/{concept_id}/items:generate",
             response_model=list[ItemOut], status_code=201)
def generate_concept_items(
    course_id: str,
    concept_id: str,
    db: DB,
    user: CurrentUser,
):
    """Extract existing numbered exercises; no model authors content (#115)."""
    owned_course(db, course_id, user.id)
    concept = course_concept(db, course_id, concept_id)
    sources = [dict(row) for row in db.execute(
        select(Source.id, Source.page, Source.text).where(Source.course_id == course_id)
        .order_by(Source.file_name, Source.page)).mappings()]
    if not sources:
        raise HTTPException(404, "no_sources")
    items = generate_items(None, concept, sources)
    if not items:
        raise HTTPException(409, "exercise_bank_insufficient")
    save_items(db, concept_id, items)
    db.commit()
    return concept_items(db, concept_id)
