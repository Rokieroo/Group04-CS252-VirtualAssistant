"""One session per request; foreign keys are enabled for SQLite as well."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alembic import command

from .cache import ReportCache

ROOT = Path(__file__).resolve().parents[3]


class Database:
    def __init__(self, url: str):
        options = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False, "timeout": 15}
            if url in {"sqlite://", "sqlite:///:memory:"}:
                options["poolclass"] = StaticPool
        self.engine = create_engine(url, **options)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.report_cache = ReportCache()
        self.sessions = sessionmaker(
            self.engine,
            expire_on_commit=False,
            info={"report_cache": self.report_cache},
        )

        @event.listens_for(self.sessions, "after_commit")
        def invalidate_reports(_):
            self.report_cache.clear()

    def create_schema(self):
        """Apply Alembic migrations; the same history the CLI and staging use."""
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
