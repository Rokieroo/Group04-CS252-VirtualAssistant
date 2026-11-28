"""Schema + migration contract tests for the Study Companion database."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import app.db as app_db
from app.db import (
    _TABLES,
    DEFAULT_DATABASE_URL,
    _as_url,
    _drop_all,
    _sqlite_path,
    get_database_url,
    get_engine,
    get_session,
    init_db,
    session_scope,
)

EXPECTED_TABLES = {
    "users",
    "courses",
    "sources",
    "concepts",
    "prereqs",
    "items",
    "cards",
    "reviews",
    "companion_events",
    # Scheduling workspace (migration 0002).
    "auth_sessions",
    "goals",
    "teams",
    "memberships",
    "invitations",
    # Core loop (migration 0004).
    "syllabi",
    "learning_outcomes",
    "assessments",
    "roadmaps",
    "roadmap_nodes",
    "resources",
    "node_resources",
    "personal_sources",
    "resource_feedback",
    "search_runs",
    # Background jobs and the shared search cache (migration 0006).
    "jobs",
    "search_cache",
    # Cost and latency of resource searches (migration 0007).
    "resource_searches",
    # Verified catalog (migration 0008).
    "institutions",
    "catalog_courses",
    "catalog_units",
    "subjects",
    "resource_subjects",
    "node_subjects",
    "resource_verifications",
    "tasks",
    "availability",
    "busy_blocks",
    "schedule_entries",
    "notifications",
    "chat_messages",
    "alembic_version",
    "catalog_embeddings",
    "roadmap_edges",
    "graph_layouts",
    "node_materials",
    "node_source_status",
    "exercises",
    "exercise_subjects",
    "node_exercises",
    "source_subjects",
    "review_cards",
    "review_logs",
    "exercise_attempts",
    "placements",
    "external_results",
    "recommendations",
    "recommendation_events",
}


@pytest.fixture()
def database_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    yield url
    get_engine(url).dispose()


@pytest.fixture()
def session(database_url):
    init_db(database_url=database_url, reset=True)
    session = get_session(database_url)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def insert_user(
    session, user_id: str = "u_1", email: str = "user1@example.com"
) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password_hash)"
        ),
        {"id": user_id, "email": email, "password_hash": "argon2-placeholder"},
    )


def insert_course(session, course_id: str = "c_1", owner_id: str = "u_1") -> None:
    session.execute(
        text(
            "INSERT INTO courses (id, owner_id, title) VALUES (:id, :owner_id, :title)"
        ),
        {"id": course_id, "owner_id": owner_id, "title": "CSC10014"},
    )


def insert_source(
    session,
    source_id: str = "s_1",
    course_id: str = "c_1",
    file_name: str = "week01.pdf",
    page: int = 1,
) -> None:
    session.execute(
        text(
            "INSERT INTO sources (id, course_id, file_name, page, text) "
            "VALUES (:id, :course_id, :file_name, :page, :text)"
        ),
        {
            "id": source_id,
            "course_id": course_id,
            "file_name": file_name,
            "page": page,
            "text": "Nội dung trang 1",
        },
    )


def insert_concept(
    session,
    concept_id: str = "k_1",
    course_id: str = "c_1",
    slug: str = "solution-ladder",
    title: str = "Solution ladder",
) -> None:
    session.execute(
        text(
            "INSERT INTO concepts (id, course_id, slug, title) "
            "VALUES (:id, :course_id, :slug, :title)"
        ),
        {"id": concept_id, "course_id": course_id, "slug": slug, "title": title},
    )


def test_init_db_creates_all_tables(database_url):
    tables = init_db(database_url=database_url, reset=True)

    assert set(tables) == EXPECTED_TABLES
    assert len(tables) == len(EXPECTED_TABLES)
    assert set(inspect(get_engine(database_url)).get_table_names()) == EXPECTED_TABLES


def test_cards_due_index_exists(database_url):
    init_db(database_url=database_url, reset=True)

    indexes = {
        index["name"]
        for index in inspect(get_engine(database_url)).get_indexes("cards")
    }
    assert "idx_cards_user_due" in indexes


def test_sources_unique_course_file_page(session):
    insert_user(session)
    insert_course(session)
    insert_source(session, source_id="s_1")
    session.commit()

    with pytest.raises(IntegrityError):
        insert_source(session, source_id="s_2")  # same (course_id, file_name, page)
    session.rollback()

    count = session.execute(text("SELECT COUNT(*) FROM sources")).scalar_one()
    assert count == 1


def test_concepts_unique_course_slug(session):
    insert_user(session)
    insert_course(session)
    insert_concept(session, concept_id="k_1")
    session.commit()

    with pytest.raises(IntegrityError):
        insert_concept(session, concept_id="k_2")  # same (course_id, slug)
    session.rollback()

    count = session.execute(text("SELECT COUNT(*) FROM concepts")).scalar_one()
    assert count == 1


def test_items_require_source_id(session):
    insert_user(session)
    insert_course(session)
    insert_concept(session)
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO items (id, concept_id, source_id, type, prompt, answer) "
                "VALUES (:id, :concept_id, :source_id, :type, :prompt, :answer)"
            ),
            {
                "id": "i_1",
                "concept_id": "k_1",
                "source_id": None,  # cite-or-refuse: must be rejected by the database
                "type": "mcq",
                "prompt": "Câu hỏi không có nguồn?",
                "answer": "A",
            },
        )
    session.rollback()

    count = session.execute(text("SELECT COUNT(*) FROM items")).scalar_one()
    assert count == 0


def test_user_defaults(session):
    insert_user(session, user_id="u_defaults", email="defaults@example.com")
    session.commit()

    row = (
        session.execute(
            text(
                "SELECT role, account_level, companion_mode, adult_verified, "
                "failed_login_attempts, birth_year, locked_until "
                "FROM users WHERE id = :id"
            ),
            {"id": "u_defaults"},
        )
        .mappings()
        .one()
    )

    assert row["role"] == "student"
    assert row["account_level"] == "university"
    assert row["companion_mode"] == "buddy"
    assert row["adult_verified"] == 0
    assert row["failed_login_attempts"] == 0
    assert row["birth_year"] is None
    assert row["locked_until"] is None


def test_sqlite_foreign_keys_are_enforced(session):
    """The PRAGMA must be enabled, otherwise this insert would silently succeed."""
    with pytest.raises(IntegrityError):
        insert_course(session, course_id="c_orphan", owner_id="u_missing")
    session.rollback()


def test_drop_all_respects_foreign_key_order_with_fk_enabled(session, database_url):
    """PostgreSQL parity: _drop_all uses no CASCADE, so _TABLES must list parents first."""
    engine = get_engine(database_url)
    position = {name: index for index, name in enumerate(_TABLES)}
    inspector = inspect(engine)
    for table in _TABLES:
        for fk in inspector.get_foreign_keys(table):
            referred = fk["referred_table"]
            if referred != table:
                assert position[referred] < position[table], (
                    f"{table} references {referred} but precedes it in _TABLES"
                )

    # A populated FK chain makes SQLite's implicit DELETE on DROP TABLE check every reference.
    assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    insert_user(session, user_id="u_fk", email="fk@example.com")
    insert_course(session, course_id="c_fk", owner_id="u_fk")
    insert_source(session, source_id="s_fk", course_id="c_fk")
    insert_concept(session, concept_id="k_fk", course_id="c_fk")
    for statement in (
        "INSERT INTO syllabi (id, course_id, raw_text) VALUES ('syl_fk', 'c_fk', 'Week 1')",
        "INSERT INTO roadmaps (id, course_id, user_id, title) VALUES ('rm_fk', 'c_fk', 'u_fk', 'Main')",
        "INSERT INTO roadmap_nodes (id, roadmap_id, type, title) VALUES ('rn_fk', 'rm_fk', 'topic', 'Intro')",
        (
            "INSERT INTO recommendations (id, user_id, node_id, resource_ref, kind, rank, score) "
            "VALUES ('rec_fk', 'u_fk', 'rn_fk', 'material:s_fk', 'user_material', 1, 0.9)"
        ),
        "INSERT INTO recommendation_events (id, recommendation_id, event) VALUES ('ev_fk', 'rec_fk', 'shown')",
    ):
        session.execute(text(statement))
    session.commit()
    session.close()

    _drop_all(engine)

    assert inspect(engine).get_table_names() == []


def test_reset_database_falls_back_to_drop_all_on_oserror(database_url, monkeypatch):
    """When SQLite file unlink fails with OSError (e.g. Windows lock), reset falls back to _drop_all."""
    init_db(database_url=database_url, reset=True)
    with session_scope(database_url) as s:
        insert_user(s, user_id="u_locked", email="locked@example.com")
        insert_course(s, course_id="c_locked", owner_id="u_locked")

    original_unlink = Path.unlink
    unlink_attempts = 0

    def locked_unlink(self, *args, **kwargs):
        nonlocal unlink_attempts
        if self.name == "test.db":
            unlink_attempts += 1
            raise PermissionError("simulated file lock")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)
    tables = init_db(database_url=database_url, reset=True)

    assert unlink_attempts == 1
    assert set(tables) == EXPECTED_TABLES
    with session_scope(database_url) as s:
        assert s.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 0


def test_session_scope_commits_rolls_back_and_closes(database_url, monkeypatch):
    init_db(database_url=database_url, reset=True)
    closed_calls = 0
    real_get_session = app_db.get_session

    def tracked_get_session(url=None):
        sess = real_get_session(url)
        real_close = sess.close

        def tracked_close():
            nonlocal closed_calls
            closed_calls += 1
            real_close()

        sess.close = tracked_close  # type: ignore[method-assign]
        return sess

    monkeypatch.setattr(app_db, "get_session", tracked_get_session)

    with session_scope(database_url) as s:
        insert_user(s, user_id="u_commit", email="commit@example.com")
    assert closed_calls == 1

    with pytest.raises(RuntimeError, match="boom"), session_scope(database_url) as s:
        insert_user(s, user_id="u_rollback", email="rollback@example.com")
        raise RuntimeError("boom")
    assert closed_calls == 2

    check = real_get_session(database_url)
    try:
        ids = check.execute(text("SELECT id FROM users ORDER BY id")).scalars().all()
        assert ids == ["u_commit"]
    finally:
        check.close()


def test_database_url_env_and_sqlite_path_resolution(tmp_path, monkeypatch):
    pg_url = "postgresql+psycopg://app:secret@localhost:5432/study"
    monkeypatch.setenv("DATABASE_URL", pg_url)
    assert get_database_url() == pg_url
    assert _as_url(None) == pg_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL
    assert _as_url(None) == DEFAULT_DATABASE_URL

    db_file = tmp_path / "nested" / "app.db"
    assert _as_url(db_file) == f"sqlite:///{db_file.as_posix()}"

    assert _sqlite_path("sqlite:///:memory:") is None
    assert _sqlite_path("sqlite://") is None
    assert _sqlite_path("sqlite:///file:memdb?mode=memory") is None
    assert _sqlite_path(pg_url) is None
    assert _sqlite_path("sqlite:///./local.db") == Path("./local.db")
