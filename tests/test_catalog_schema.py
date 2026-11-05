"""Migration 0008_verified_catalog: constraints, cascades and the backfill (issue #95)."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alembic import command
from assistant.backend.database import Database
from assistant.backend.models import (
    Course,
    NodeSubject,
    Resource,
    ResourceSubject,
    Roadmap,
    RoadmapNode,
    Subject,
    User,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sessions(database_url):
    database = Database(database_url)
    database.create_schema()
    yield database.sessions
    database.engine.dispose()


def resource(url, title="A"):
    return Resource(url=url, canonical_url=url.rstrip("/"), title=title)


def test_two_resources_cannot_share_a_canonical_url(sessions):
    with sessions() as db:
        db.add(resource("https://a.edu/x"))
        db.commit()
        db.add(resource("https://a.edu/x/", title="B"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_new_resources_start_pending(sessions):
    with sessions() as db:
        db.add(resource("https://a.edu/x"))
        db.commit()
        assert db.scalars(select(Resource.verification_status)).one() == "pending"


def test_deleting_a_roadmap_drops_node_labels_but_keeps_the_shared_catalog(sessions):
    with sessions() as db:
        user = User(email="minh@example.com", password_hash="x")
        db.add(user)
        db.flush()
        course = Course(owner_id=user.id, title="Algo")
        db.add(course)
        db.flush()
        roadmap = Roadmap(course_id=course.id, user_id=user.id, title="Algo")
        db.add(roadmap)
        db.flush()
        node = RoadmapNode(roadmap_id=roadmap.id, type="topic", title="Sorting")
        subject = Subject(slug="cs.algorithms.sorting", name="Sorting")
        shared = resource("https://a.edu/sort")
        db.add_all([node, subject, shared])
        db.flush()
        db.add_all([
            NodeSubject(node_id=node.id, subject_id=subject.id, method="rule"),
            ResourceSubject(resource_id=shared.id, subject_id=subject.id, method="rule"),
        ])
        db.commit()

        db.delete(roadmap)
        db.commit()

        assert db.scalars(select(NodeSubject)).all() == []
        assert db.scalars(select(Resource.id)).all() == [shared.id]
        assert db.scalars(select(Subject.id)).all() == [subject.id]
        assert db.scalars(select(ResourceSubject.resource_id)).all() == [shared.id]


# A learner's data as it stands at 0007, before the catalog exists.
_ROWS_AT_0007 = (
    "INSERT INTO users (id, email, password_hash) VALUES ('u1', 'u@example.com', 'x')",
    "INSERT INTO courses (id, owner_id, title) VALUES ('c1', 'u1', 'Algo')",
    "INSERT INTO roadmaps (id, course_id, user_id, title) VALUES ('r1', 'c1', 'u1', 'Algo')",
    "INSERT INTO roadmap_nodes (id, roadmap_id, type, title) VALUES ('n1', 'r1', 'topic', 'Sort')",
    "INSERT INTO resources (id, url, title) VALUES ('s1', 'https://a.edu/sort', 'Sort')",
    "INSERT INTO node_resources (node_id, resource_id) VALUES ('n1', 's1')",
)


def test_upgrade_backfills_and_downgrade_keeps_existing_rows(database_url, tmp_path):
    if database_url == "sqlite://":  # each connection to it would be a new database
        database_url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    # Foreign keys on, as the app runs: a rebuild of resources would cascade.
    engine = Database(database_url).engine
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007_search_metrics")
        for row in _ROWS_AT_0007:
            connection.exec_driver_sql(row)

        command.upgrade(config, "head")
        backfilled = connection.exec_driver_sql(
            "SELECT canonical_url, verification_status FROM resources"
        ).one()
        assert tuple(backfilled) == ("https://a.edu/sort", "pending")

        command.downgrade(config, "0007_search_metrics")
        command.upgrade(config, "head")
        links = connection.exec_driver_sql("SELECT COUNT(*) FROM node_resources")
        assert links.scalar_one() == 1
    engine.dispose()
