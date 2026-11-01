"""Courses, page-level PDF sources (UC-01, #13), concept proposals (UC-02, #9) and cited items (UC-03, #10)."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.concepts.extract import extract_concepts, save_concepts
from app.concepts.visual import read_visuals
from app.items.generate import generate_items, save_items
from app.llm import LLMClient, get_client, get_vision_client

from .dependencies import DB, CurrentUser
from .ingest import MAX_UPLOAD_BYTES, InvalidPdf, extract_pages, looks_scanned
from .models import Course, Source
from .schemas import (
    ConceptGraphOut,
    CourseCreate,
    CourseOut,
    ItemOut,
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
    db: DB,
    user: CurrentUser,
    vision: Annotated[LLMClient, Depends(get_vision_client)],
):
    owned_course(db, course_id, user.id)
    # Browsers may send a Windows path; keep only the base name.
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not 1 <= len(name) <= 255:
        raise HTTPException(422, "invalid_file_name")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file_too_large")
    if not data:
        raise HTTPException(400, "invalid_pdf")
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise HTTPException(415, "not_pdf")
    try:
        pages = extract_pages(data)
    except InvalidPdf:
        raise HTTPException(400, "invalid_pdf") from None
    # A re-upload revises the notes kept from last time; a failed chunk keeps them.
    previous = [""] * len(pages)
    for number, note in db.execute(select(Source.page, Source.visual_notes).where(
            Source.course_id == course_id, Source.file_name == name)):
        if number <= len(pages):
            previous[number - 1] = note or ""
    notes = read_visuals(vision, data, len(pages), previous)
    # Re-uploading the same file name replaces its pages.
    db.execute(
        delete(Source).where(Source.course_id == course_id, Source.file_name == name)
    )
    db.add_all(
        Source(course_id=course_id, file_name=name, page=number, text=text,
               visual_notes=note or None)
        for number, (text, note) in enumerate(zip(pages, notes, strict=True), start=1)
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "upload_in_progress") from None
    return UploadOut(
        file_name=name,
        pages=len(pages),
        status="processed",
        warning="scanned_pdf" if looks_scanned(pages) else None,
    )


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
    rows = db.execute(text(
        "SELECT i.id, i.type, i.prompt, i.choices, i.answer, i.rubric, i.source_id, i.status, "
        "s.page, s.file_name FROM items i JOIN sources s ON s.id = i.source_id "
        "WHERE i.concept_id = :id ORDER BY s.file_name, s.page, i.type, i.id"),
        {"id": concept_id}).mappings()
    return [{**row, "choices": json.loads(row["choices"] or "[]"),
             "rubric": json.loads(row["rubric"] or "[]")} for row in rows]


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
    llm: Annotated[LLMClient, Depends(get_client)],
):
    """Write cited practice items for one concept, store them as drafts and return all of the
    concept's items (UC-03, issue #10)."""
    owned_course(db, course_id, user.id)
    concept = course_concept(db, course_id, concept_id)
    sources = [dict(row) for row in db.execute(
        select(Source.id, Source.page, Source.text).where(Source.course_id == course_id)
        .order_by(Source.file_name, Source.page)).mappings()]
    if not sources:
        raise HTTPException(404, "no_sources")
    items = generate_items(llm, concept, sources)
    if not items:  # every LLM call failed, or every item was refused for lack of a citation
        raise HTTPException(503, "items_unavailable")
    save_items(db, concept_id, items)
    db.commit()
    return concept_items(db, concept_id)
