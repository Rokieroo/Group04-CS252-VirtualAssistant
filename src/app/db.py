"""Application database helpers.

The connection URL comes from ``DATABASE_URL`` (default: ``sqlite:///./local.db``).
SQLite is used for local development and tests; PostgreSQL 16 is used in
staging/production. The canonical schema lives in ``db/schema.sql`` and is kept
in sync with the Alembic migrations (enforced by ``tests/test_schema_sync.py``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./local.db"
ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# Load a local .env if python-dotenv is available. Existing environment
# variables always win (override=False is the default).
try:  # pragma: no cover - optional convenience for developers
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover - python-dotenv is an optional install
    pass

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

_ENGINES: dict[str, Engine] = {}
_SESSION_FACTORIES: dict[str, sessionmaker[Session]] = {}
_LOCK = RLock()

# Tables in dependency order. Used for a portable reset on non-file databases.
_TABLES = (
    "users",
    "search_cache",
    "institutions",
    "subjects",
    "courses",
    "companion_events",
    "auth_sessions",
    "goals",
    "teams",
    "jobs",
    "catalog_courses",
    "availability",
    "busy_blocks",
    "chat_messages",
    "sources",
    "concepts",
    "memberships",
    "invitations",
    "syllabi",
    "roadmaps",
    "resources",
    "prereqs",
    "learning_outcomes",
    "assessments",
    "roadmap_nodes",
    "resource_feedback",
    "catalog_units",
    "resource_subjects",
    "resource_verifications",
    "exercises",
    "items",
    "node_resources",
    "resource_searches",
    "node_subjects",
    "tasks",
    "catalog_embeddings",
    "node_source_status",
    "roadmap_edges",
    "graph_layouts",
    "node_materials",
    "source_subjects",
    "exercise_subjects",
    "node_exercises",
    "cards",
    "reviews",
    "review_cards",
    "review_logs",
    "search_runs",
    "schedule_entries",
    "notifications",
    "external_results",
    "recommendations",
    "recommendation_events",
)


def get_database_url() -> str:
    """Return the configured database URL, read from the environment each time."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _as_url(database_url: str | Path | None) -> str:
    if database_url is None:
        return get_database_url()
    if isinstance(database_url, Path):
        return f"sqlite:///{database_url.as_posix()}"
    return database_url


def _sqlite_path(database_url: str) -> Path | None:
    """Return the SQLite file path, or None for memory/URI databases."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return None
    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return None
    return Path(database)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite needs foreign-key enforcement enabled per connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()


def get_engine(database_url: str | Path | None = None) -> Engine:
    """Create (or reuse) a SQLAlchemy engine for ``database_url``.

    SQLite engines get ``PRAGMA foreign_keys = ON`` on every connection.
    """
    url = _as_url(database_url)
    with _LOCK:
        cached = _ENGINES.get(url)
        if cached is not None:
            return cached

        sqlite_file = _sqlite_path(url)
        if sqlite_file is not None:
            sqlite_file.parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(url, future=True)
        if engine.dialect.name == "sqlite":
            event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        _ENGINES[url] = engine
        return engine


def get_sessionmaker(database_url: str | Path | None = None) -> sessionmaker[Session]:
    """Return a session factory bound to ``database_url``."""
    url = _as_url(database_url)
    with _LOCK:
        factory = _SESSION_FACTORIES.get(url)
        if factory is not None:
            return factory
        factory = sessionmaker(
            bind=get_engine(url), expire_on_commit=False, future=True
        )
        _SESSION_FACTORIES[url] = factory
        return factory


def get_session(database_url: str | Path | None = None) -> Session:
    """Return a new session. The caller is responsible for closing it."""
    return get_sessionmaker(database_url)()


def get_connection(database_url: str | Path | None = None) -> Connection:
    """Return a new connection. The caller is responsible for closing it."""
    return get_engine(database_url).connect()


@contextmanager
def session_scope(database_url: str | Path | None = None) -> Iterator[Session]:
    """Provide a transaction-scoped session (commit on success, rollback on error)."""
    session = get_session(database_url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def connection_scope(database_url: str | Path | None = None) -> Iterator[Connection]:
    """Provide a connection inside a transaction."""
    with get_engine(database_url).begin() as connection:
        yield connection


def _sql_statements(sql: str) -> list[str]:
    """Split the simple DDL file into statements without breaking comments."""
    lines = []
    for line in sql.splitlines():
        code, _, _comment = line.partition("--")
        lines.append(code)
    return [
        statement.strip()
        for statement in "\n".join(lines).split(";")
        if statement.strip()
    ]


def _drop_all(engine: Engine) -> None:
    with engine.begin() as connection:
        for table in reversed((*_TABLES, "alembic_version")):
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')


def _reset_database(engine: Engine, database_url: str) -> None:
    sqlite_file = _sqlite_path(database_url)
    if sqlite_file is not None:
        engine.dispose()
        try:
            sqlite_file.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(f"{sqlite_file}{suffix}").unlink(missing_ok=True)
            return
        except OSError:
            # A file may be locked on Windows; dropping the known tables is a
            # safe fallback and works the same way for PostgreSQL.
            pass
    _drop_all(engine)


def init_db(reset: bool = False, database_url: str | Path | None = None) -> list[str]:
    """Create the schema from ``db/schema.sql`` and return the table names.

    ``reset=True`` removes the local SQLite file (or drops the known tables on
    other databases) before creating a clean schema.
    """
    url = _as_url(database_url)
    engine = get_engine(url)
    if reset:
        _reset_database(engine, url)

    with engine.begin() as connection:
        for statement in _sql_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            connection.exec_driver_sql(statement)

    return list_tables(url)


def list_tables(database_url: str | Path | None = None) -> list[str]:
    """Return the sorted table names currently present in the database."""
    return sorted(inspect(get_engine(database_url)).get_table_names())


def __getattr__(name: str):
    """Keep ``app.db.engine`` / ``app.db.SessionLocal`` convenient and current."""
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_sessionmaker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
