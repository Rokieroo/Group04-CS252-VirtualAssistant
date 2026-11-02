from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_migration_preserves_existing_concept_and_defaults_to_no_provenance(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0001_initial")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,email,password_hash) VALUES ('u','u@example.com','test')"))
            connection.execute(text("INSERT INTO courses (id,owner_id,title) VALUES ('c','u','CS252')"))
            connection.execute(text("INSERT INTO concepts (id,course_id,slug,title,source_pages) "
                                    "VALUES ('k','c','topic','Topic','[1]')"))
        command.upgrade(config, "head")
        assert "source_ids" in {column["name"] for column in inspect(engine).get_columns("concepts")}
        with engine.connect() as connection:
            row = connection.execute(text("SELECT title,source_pages,source_ids FROM concepts WHERE id='k'")).one()
            assert tuple(row) == ("Topic", "[1]", "[]")
    finally:
        engine.dispose()
