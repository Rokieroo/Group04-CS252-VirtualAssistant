"""Run: python -m uvicorn assistant.backend.main:app --app-dir src --reload."""

from contextlib import asynccontextmanager, nullcontext
from threading import RLock

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.companion import ChatProvider, Companion
from app.ingest import MAX_UPLOAD_BYTES

from . import (
    routes_ai,
    routes_auth,
    routes_core,
    routes_courses,
    routes_jobs,
    routes_schedule,
    routes_tasks,
    routes_teams,
)
from .config import Settings
from .database import Database
from .models import utcnow

API = "/api/v1"
# Multipart framing around the file; anything larger is rejected before parsing.
_UPLOAD_OVERHEAD = 64 * 1024


def create_app(settings: Settings | None = None, *, now=utcnow, ai_transport=None):
    settings = settings or Settings.from_env()
    database = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        database.create_schema()
        yield
        database.engine.dispose()

    application = FastAPI(
        title="Pathly Study Companion API",
        version="0.3.0",
        lifespan=lifespan,
        description="CS252 Group 04 — courses and PDF ingest, accounts, scheduling "
        "workspace and AI companion. Register or log in, then use Authorize with the "
        "returned access_token.",
    )
    application.state.database = database
    application.state.settings = settings
    application.state.now = now
    application.state.companion = Companion(
        ChatProvider(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_timeout_seconds,
            ai_transport,
        )
        if settings.llm_api_key and settings.llm_model
        else None
    )
    # SQLite has no row locks, so one process-wide lock serializes schedule writes.
    # PostgreSQL already serializes them per user with SELECT ... FOR UPDATE.
    application.state.schedule_lock = (
        RLock() if database.engine.dialect.name == "sqlite" else nullcontext()
    )

    @application.middleware("http")
    async def limit_upload_size(request, call_next):
        if request.method == "POST" and request.url.path.endswith("/sources"):
            length = request.headers.get("content-length", "")
            if not length.isdigit():
                return JSONResponse({"detail": "length_required"}, status_code=411)
            if int(length) > MAX_UPLOAD_BYTES + _UPLOAD_OVERHEAD:
                return JSONResponse({"detail": "file_too_large"}, status_code=413)
        return await call_next(request)

    # Added last so it is outermost: CORS headers also reach the 411/413 replies.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for router in (
        routes_auth.router,
        routes_courses.router,
        routes_core.router,
        routes_tasks.router,
        routes_schedule.router,
        routes_teams.router,
        routes_ai.router,
        routes_jobs.router,
    ):
        application.include_router(router, prefix=API)

    @application.get(API + "/health", tags=["Health"])
    def health():
        return {
            "status": "ok",
            "ai_provider": "llm" if settings.llm_model else "offline",
        }

    return application


def __getattr__(name):
    # Built on first access (uvicorn), so importing create_app reads no env or .env.
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
