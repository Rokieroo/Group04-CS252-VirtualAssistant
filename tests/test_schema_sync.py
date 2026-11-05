"""db/schema.sql, the Alembic migrations and the backend ORM must describe one schema."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.db import _TABLES, get_engine, init_db
from assistant.backend.database import Database
from assistant.backend.models import Base

ROOT = Path(__file__).resolve().parents[1]


# Same types, different spellings: Alembic on SQLite vs. portable SQL.
_SAME_TYPE = {
    "DATETIME": "TIMESTAMP",
    "FLOAT": "REAL",
    "DOUBLE": "REAL",
    "DOUBLE PRECISION": "REAL",
}


def _shape(engine):
    found = inspect(engine)
    shape = {}
    for table in found.get_table_names():
        keys = set(found.get_pk_constraint(table)["constrained_columns"])
        shape[table] = {
            column["name"]: (
                _SAME_TYPE.get(
                    str(column["type"]).upper(), str(column["type"]).upper()
                ),
                # SQLite reports non-INTEGER primary keys as nullable; they are not.
                column["nullable"] and column["name"] not in keys,
            )
            for column in found.get_columns(table)
        }
    return shape


def _migrated(url):
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = create_engine(url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine


def test_schema_sql_matches_migrations(tmp_path):
    from_sql = tmp_path / "sql.db"
    init_db(database_url=from_sql, reset=True)
    migrated = _migrated(f"sqlite:///{(tmp_path / 'alembic.db').as_posix()}")
    assert _shape(get_engine(from_sql)) == _shape(migrated)
    with get_engine(from_sql).connect() as connection:
        stamped = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
        assert (
            stamped.scalar_one()
            == command.ScriptDirectory.from_config(
                Config(str(ROOT / "alembic.ini"))
            ).get_current_head()
        )


def test_orm_models_match_migrations(tmp_path):
    engine = _migrated(f"sqlite:///{(tmp_path / 'orm.db').as_posix()}")
    mapped = set(Base.metadata.tables)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diffs = compare_metadata(context, Base.metadata)
    # The ORM maps only some tables; ignore differences in the ones it does not own.
    # SQLAlchemy's SQLite FK_PATTERN parses table-level FOREIGN KEY syntax only;
    # native ADD COLUMN ... REFERENCES has correct PRAGMA actions but loses those
    # actions in reflection. Check the actual constraints below instead of
    # rebuilding referenced parent tables (which would cascade-delete child data).
    assert [
        diff
        for diff in diffs
        if _table_of(diff) in mapped and diff[0] not in {"add_fk", "remove_fk"}
    ] == []
    _assert_sqlite_foreign_keys(engine)


def _assert_sqlite_foreign_keys(engine):
    with engine.connect() as connection:
        for table in Base.metadata.tables.values():
            actual = {
                (r[3], r[2], r[4], r[6])
                for r in connection.exec_driver_sql(
                    f'PRAGMA foreign_key_list("{table.name}")'
                )
            }
            expected = {
                (
                    fk.parent.name,
                    fk.column.table.name,
                    fk.column.name,
                    fk.ondelete or "NO ACTION",
                )
                for fk in table.foreign_keys
            }
            assert actual == expected, table.name


def test_reset_knows_every_table(tmp_path):
    # A reset on PostgreSQL drops _TABLES in reverse; a missing table blocks the drop.
    created = init_db(database_url=tmp_path / "all.db", reset=True)
    assert set(created) == {*_TABLES, "alembic_version"}


def test_backend_accepts_a_database_created_by_the_dev_cli(tmp_path):
    path = tmp_path / "cli.db"
    init_db(database_url=path, reset=True)
    get_engine(path).dispose()
    Database(f"sqlite:///{path.as_posix()}").create_schema()  # must be a no-op


def _table_of(diff):
    if isinstance(
        diff, list
    ):  # column modifications: [("modify_type", schema, table, ...)]
        return diff[0][2]
    kind, item = diff[0], diff[1]
    if kind.endswith("_table"):
        return item.name
    if kind.endswith("_column"):
        return diff[2]
    return item.table.name  # indexes and constraints
