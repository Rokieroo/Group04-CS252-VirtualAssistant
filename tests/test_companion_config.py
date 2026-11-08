from assistant.backend.config import Settings


def test_backend_shares_database_url_but_not_course_llm_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///course-app.db")
    monkeypatch.setenv("LLM_API_KEY", "course-provider-key")
    monkeypatch.setenv("LLM_MODEL", "course-model")
    for suffix in ("API_KEY", "MODEL", "BASE_URL", "TIMEOUT_SECONDS"):
        monkeypatch.delenv("COMPANION_LLM_" + suffix, raising=False)
    config = Settings.from_env()
    # One database (and one Alembic history) for the whole app.
    assert config.database_url == "sqlite:///course-app.db"
    assert config.llm_api_key == "" and config.llm_model == ""


def test_hosted_postgres_url_uses_psycopg_driver(monkeypatch):
    for given in ("postgres://u:p@host/db", "postgresql://u:p@host/db"):
        monkeypatch.setenv("DATABASE_URL", given)
        assert Settings.from_env().database_url == "postgresql+psycopg://u:p@host/db"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
    assert Settings.from_env().database_url == "postgresql+psycopg://u:p@host/db"


def test_backend_reads_companion_provider_and_session_lifetime(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SESSION_MINUTES", raising=False)
    monkeypatch.setenv("COMPANION_LLM_API_KEY", "workspace-provider-key")
    monkeypatch.setenv("COMPANION_LLM_MODEL", "workspace-model")
    config = Settings.from_env()
    assert config.database_url == "sqlite:///./local.db"
    assert config.session_minutes == 60
    assert config.llm_api_key == "workspace-provider-key"
    assert config.llm_model == "workspace-model"
