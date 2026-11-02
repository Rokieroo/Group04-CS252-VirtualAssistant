"""Environment settings; no credentials or external calls are needed locally."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _with_psycopg_driver(url: str) -> str:
    # Hosted Postgres (e.g. Neon on Vercel) hands out postgres:// URLs; SQLAlchemy
    # would pick psycopg2 for those, but only psycopg 3 is installed.
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme) :]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./local.db"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    session_minutes: int = 60
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = field(default="", repr=False)
    llm_model: str = ""
    llm_timeout_seconds: float = 20

    def __post_init__(self):
        if not 5 <= self.session_minutes <= 43200:
            raise ValueError("SESSION_MINUTES must be between 5 and 43200")
        if not 1 <= self.llm_timeout_seconds <= 60:
            raise ValueError("COMPANION_LLM_TIMEOUT_SECONDS must be between 1 and 60")
        if bool(self.llm_api_key) != bool(self.llm_model):
            raise ValueError(
                "Set both COMPANION_LLM_API_KEY and COMPANION_LLM_MODEL, or leave both empty"
            )

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            # One database for the whole app, shared with Alembic and the dev CLI.
            database_url=_with_psycopg_driver(
                os.getenv("DATABASE_URL", "sqlite:///./local.db")
            ),
            cors_origins=tuple(
                value.strip()
                for value in os.getenv(
                    "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
                ).split(",")
                if value.strip()
            ),
            session_minutes=int(os.getenv("SESSION_MINUTES", "60")),
            llm_base_url=os.getenv(
                "COMPANION_LLM_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            llm_api_key=os.getenv("COMPANION_LLM_API_KEY", ""),
            llm_model=os.getenv("COMPANION_LLM_MODEL", ""),
            llm_timeout_seconds=float(os.getenv("COMPANION_LLM_TIMEOUT_SECONDS", "20")),
        )
