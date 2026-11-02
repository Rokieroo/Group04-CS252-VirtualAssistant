"""Run: python -m uvicorn app.api.main:app --app-dir src."""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import get_database_url, get_engine, init_db
from app.ingest.pdf import MAX_PDF_BYTES, PDFError, extract_pdf

from .auth import Database, User, fail, owned_course
from .study import router as study_router
from .upload_limit import UploadLimitMiddleware


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    level: str = Field(default="university", pattern=r"^(university|k12)$")
    language: str = Field(default="vi", min_length=2, max_length=20)


def create_app(database_url=None, *, llm_client=None):
    url = database_url or get_database_url()

    @asynccontextmanager
    async def lifespan(application):
        init_db(database_url=url)
        if "source_ids" not in {column["name"] for column in inspect(get_engine(url)).get_columns("concepts")}:
            raise RuntimeError("Study database needs migration: run alembic upgrade head. See docs/minh-slide-pipeline.md.")
        yield

    application = FastAPI(title="Study Companion", version="0.1.0", lifespan=lifespan)
    application.state.database_url = url
    application.state.llm_client = llm_client
    application.include_router(study_router)
    application.add_middleware(UploadLimitMiddleware)

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": exc.detail}
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request fields."}},
                            status_code=422)

    @application.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @application.post("/api/v1/courses", status_code=201)
    def create_course(data: CourseInput, user: User, database: Database):
        row = {"id": "c_" + uuid4().hex, "owner_id": user, **data.model_dump()}
        database.execute(text("INSERT INTO courses (id,owner_id,title,level,language) "
                              "VALUES (:id,:owner_id,:title,:level,:language)"), row)
        database.commit()
        return row

    @application.get("/api/v1/courses")
    def list_courses(user: User, database: Database):
        rows = database.execute(text("SELECT * FROM courses WHERE owner_id=:owner ORDER BY id"),
                                {"owner": user}).mappings().all()
        return {"courses": [dict(row) for row in rows]}

    @application.get("/api/v1/courses/{course_id}/sources")
    def list_sources(course_id: str, user: User, database: Database):
        owned_course(database, course_id, user)
        rows = database.execute(text("SELECT * FROM sources WHERE course_id=:id ORDER BY file_name,page"),
                                {"id": course_id}).mappings().all()
        return {"sources": [dict(row) for row in rows]}

    @application.post("/api/v1/courses/{course_id}/sources", status_code=201)
    async def upload_source(course_id: str, file: UploadFile,
                            user: User, database: Database):
        owned_course(database, course_id, user)
        file_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not file_name or len(file_name) > 255:
            fail(415, "not_pdf", "A PDF filename is required.")
        data = bytearray()
        try:
            while chunk := await file.read(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_PDF_BYTES:
                    fail(413, "file_too_large", "PDF limit is 20 MB.")
        finally:
            await file.close()
        try:
            pages, warnings = extract_pdf(bytes(data), file_name)
        except PDFError as exc:
            fail(exc.status, exc.code, "Upload a readable PDF of at most 20 MB.")
        try:
            database.execute(text("INSERT INTO sources (id,course_id,file_name,page,text) "
                                  "VALUES (:id,:course_id,:file_name,:page,:text)"), [
                {"id": "s_" + uuid4().hex, "course_id": course_id, "file_name": file_name,
                 "page": number, "text": value} for number, value in enumerate(pages, 1)
            ])
            database.commit()
        except IntegrityError:
            database.rollback()
            fail(409, "source_conflict", "This filename already exists; use a different filename.")
        return {"file_name": file_name, "pages": len(pages), "status": "processed", "warnings": warnings}

    return application


app = create_app()
