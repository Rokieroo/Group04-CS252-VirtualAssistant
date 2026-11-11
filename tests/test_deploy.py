"""Production server setup (issue #18): settings, compose file and SQL roles."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from assistant.backend.config import Settings
from assistant.backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose.prod.yml"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("On", True), ("0", False), ("no", False), (" off ", False)],
)
def test_run_migrations_flag(monkeypatch, value, expected):
    monkeypatch.setenv("RUN_MIGRATIONS", value)
    assert Settings.from_env().run_migrations is expected


def test_run_migrations_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("RUN_MIGRATIONS", "maybe")
    with pytest.raises(ValueError, match="RUN_MIGRATIONS"):
        Settings.from_env()


def test_api_skips_migrations_when_told(tmp_path):
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    with TestClient(create_app(Settings(database_url=url, run_migrations=False))):
        pass
    assert inspect(create_engine(url)).get_table_names() == []


def test_api_migrates_by_default(tmp_path):
    url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    with TestClient(create_app(Settings(database_url=url))):
        pass
    assert "alembic_version" in inspect(create_engine(url)).get_table_names()


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_database_is_never_published(compose):
    for name in ("db", "migrate", "backup"):
        service = compose["services"][name]
        assert "ports" not in service, name
        assert service["networks"] == ["internal"], name
    assert compose["networks"]["internal"]["internal"] is True


def test_only_the_web_proxy_publishes_ports(compose):
    published = {name for name, s in compose["services"].items() if s.get("ports")}
    assert published == {"web"}


def test_secrets_are_required(compose):
    text = COMPOSE.read_text(encoding="utf-8")
    for secret in ("POSTGRES_SUPERUSER_PASSWORD", "PATHLY_OWNER_PASSWORD",
                   "PATHLY_APP_PASSWORD", "DOMAIN"):
        assert f"${{{secret}:?" in text, secret
    assert "study_pass" not in text


def test_runtime_logs_in_as_app_role_and_owner_only_migrates(compose):
    services = compose["services"]
    for name in ("api", "worker"):
        env = services[name]["environment"]
        assert env["DATABASE_URL"].startswith("postgresql+psycopg://pathly_app:"), name
        assert env["RUN_MIGRATIONS"] == "0", name
    assert services["migrate"]["environment"]["DATABASE_URL"].startswith(
        "postgresql+psycopg://pathly_owner:"
    )
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )


def test_roles_sql_keeps_the_app_role_off_the_schema():
    sql = (ROOT / "db/postgres/roles.sql").read_text(encoding="utf-8")
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pathly_app" in sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE pathly_owner" in sql
    assert "SUPERUSER" in sql and "NOSUPERUSER" in sql
    # Passwords come from psql variables, never from the file.
    assert "PASSWORD '" not in sql
