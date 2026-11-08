"""Vercel entrypoint: Vercel resolves modules from the project root, but the code lives in src/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from assistant.backend.main import app  # noqa: F401 - re-exported for Vercel
