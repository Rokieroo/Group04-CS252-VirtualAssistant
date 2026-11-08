"""Isolated #56 browser-test backend: in-memory database, fake vision, no real accounts."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ["LLM_PROVIDER"] = "fake"

import docx
import uvicorn

from assistant.backend.config import Settings
from assistant.backend.main import create_app

scratch = ROOT / "ui" / ".tmp"
scratch.mkdir(exist_ok=True)
document = docx.Document()
for line in (ROOT / "eval/syllabus/01_csc10014_problem_framing.txt").read_text(encoding="utf-8").splitlines():
    document.add_paragraph(line)
document.save(scratch / "CSC10014.docx")
app = create_app(Settings(database_url="sqlite://", cors_origins=("http://127.0.0.1:5182",)))
uvicorn.run(app, host="127.0.0.1", port=8012, log_level="warning")
