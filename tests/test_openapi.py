"""docs/openapi.json is the contract the UI codes against; it must match the app."""

import json
from pathlib import Path

from assistant.backend.config import Settings
from assistant.backend.main import create_app

CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def test_committed_openapi_matches_the_app():
    current = create_app(Settings(database_url="sqlite://")).openapi()
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == current, (
        "API changed: run `python scripts/export_openapi.py` and commit docs/openapi.json"
    )
