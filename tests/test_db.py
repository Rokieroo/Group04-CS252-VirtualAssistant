"""Schema + migration contract tests for the Study Companion database."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import get_engine, get_session, init_db

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
    "catalog_embeddings", "roadmap_edges", "graph_layouts", "node_materials", "node_source_status",
    "exercises", "exercise_subjects", "node_exercises",
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


def insert_user(session, user_id: str = "u_1", email: str = "user1@example.com") -> None:
    session.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :password_hash)"),
        {"id": user_id, "email": email, "password_hash": "argon2-placeholder"},
    )


def insert_course(session, course_id: str = "c_1", owner_id: str = "u_1") -> None:
    session.execute(
        text("INSERT INTO courses (id, owner_id, title) VALUES (:id, :owner_id, :title)"),
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

    indexes = {index["name"] for index in inspect(get_engine(database_url)).get_indexes("cards")}
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

    row = session.execute(
        text(
            "SELECT role, account_level, companion_mode, adult_verified, "
            "failed_login_attempts, birth_year, locked_until "
            "FROM users WHERE id = :id"
        ),
        {"id": "u_defaults"},
    ).mappings().one()

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
