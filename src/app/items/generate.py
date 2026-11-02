"""Practice question generation with cite-or-refuse (issue #10, spec 3.1, 10.2).

For one concept, BM25 picks the top-3 slide pages; the LLM writes 3-5 items, each citing
one of those pages by ``source_id``. An item citing any other page, a malformed MCQ, a
short answer without a 2-4 criterion rubric, or an item with contact details is dropped
before anything is stored. Slide text is data only, never instructions (spec 10.6).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from app.concepts.extract import _data
from app.llm import LLMClient, RetryableError
from app.retrieval import retrieve_top_k

log = logging.getLogger("app.items")

PROMPT = Path(__file__).parent / "prompts" / "generate_v1.txt"
TOP_K = 3
MAX_ITEMS = 5
TYPES = ("mcq", "short")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# +84 912 345 678, 0912.345.678, 028 3835 4266: a leading + or 0, then 9-11 digits.
PHONE = re.compile(r"(?<![\w+])(?:\+\d{1,3}|0)(?:[\s.-]?\d){8,10}(?!\d)")

STRINGS = {"type": "array", "items": {"type": "string"}}
ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(TYPES)},
                    "prompt": {"type": "string"},
                    "choices": STRINGS,
                    "answer": {"type": "string"},
                    "rubric": STRINGS,
                    "source_id": {"type": "string"},
                },
                "required": ["type", "prompt", "choices", "answer", "rubric", "source_id"],
            },
        }
    },
    "required": ["items"],
}


def pick_pages(concept: dict, sources: list[dict]) -> list[dict]:
    """Top-3 BM25 pages for the concept, ranked among the pages it cites (``source_pages``)
    when it has any, else among all pages; its other cited pages fill the rest."""
    cited = set(concept.get("source_pages") or [])
    own = [{"id": str(s["id"]), "page": s["page"], "text": s["text"]}
           for s in sources if s["page"] in cited]
    hits = retrieve_top_k(f"{concept['title']} {concept['summary']}", own or sources,
                          top_k=TOP_K)
    picked = [{"id": h.source_id, "page": h.page, "text": h.text} for h in hits]
    ids = {p["id"] for p in picked}
    return (picked + [p for p in own if p["id"] not in ids])[:TOP_K]


def parse_items(answer: str, source_ids: set[str]) -> list[dict]:
    """Validate the LLM's JSON answer; raises ValueError when the answer is unusable.

    Each item that breaks a rule is dropped on its own, so nothing reaches the database
    without a citation to a page the model was shown.
    """
    data = json.loads(answer)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError('expected {"items": [...]}')  # noqa: TRY004
    items = []
    for raw in data["items"]:
        item = _valid(raw, source_ids) if isinstance(raw, dict) else None
        if item is None:
            log.info("items: dropped %r", raw)
        else:
            items.append(item)
    return items[:MAX_ITEMS]


def generate_items(llm: LLMClient, concept: dict, sources: list[dict]) -> list[dict]:
    """Write items for one concept from the course's slide pages (rows with id, page, text).

    Returns [] (refuse) when no page matches the concept or the LLM answer is unusable.
    """
    pages = pick_pages(concept, sources)
    if not pages:
        log.warning("items: no source page for concept %r", concept["title"])
        return []
    slides = "\n".join(f"[source_id={p['id']}, page {p['page']}] {p['text']}" for p in pages)
    prompt = (f"<concept>\n{_data(concept['title'] + ' | ' + concept['summary'])}\n</concept>\n"
              f"<slide_text>\n{_data(slides)}\n</slide_text>")
    try:
        answer = llm.complete(prompt, system=PROMPT.read_text(encoding="utf-8"),
                              json_schema=ITEMS_SCHEMA, max_tokens=8192,
                              temperature=0.2).text  # thinking counts
        return parse_items(answer, {p["id"] for p in pages})
    except (ValueError, RetryableError) as exc:  # bad JSON, or quota/network after retries
        log.warning("items: skipped concept %r: %s", concept["title"], exc)
        return []


def save_items(db, concept_id: str, items: list[dict]) -> list[dict]:
    """Store items as ungraded drafts; ``db`` is a SQLAlchemy Session or Connection and the
    caller commits."""
    saved = []
    for item in items:
        row = {**item, "id": str(uuid4()), "concept_id": concept_id,
               "choices": json.dumps(item["choices"], ensure_ascii=False)
               if item["choices"] else None,
               "rubric": json.dumps(item["rubric"], ensure_ascii=False)
               if item["rubric"] else None}
        db.execute(text(
            "INSERT INTO items (id, concept_id, source_id, type, prompt, choices, answer, rubric, "
            "graded, status) VALUES (:id, :concept_id, :source_id, :type, :prompt, :choices, "
            ":answer, :rubric, 0, 'draft')"), row)
        saved.append({**item, "id": row["id"]})
    return saved


def _valid(raw: dict, source_ids: set[str]) -> dict | None:
    """The cleaned item, or None when it must be dropped."""
    kind, source_id = raw.get("type"), raw.get("source_id")
    prompt, answer = _text(raw.get("prompt")), _text(raw.get("answer"))
    choices, rubric = _texts(raw.get("choices")), _texts(raw.get("rubric"))
    if kind not in TYPES or source_id not in source_ids or not (prompt and answer):
        return None
    if kind == "mcq":
        if (choices is None or len(choices) != 4 or answer not in choices
                or len({c.casefold() for c in choices}) != 4):
            return None
        rubric = []
    else:
        if rubric is None or not 2 <= len(rubric) <= 4:
            return None
        choices = []
    if any(EMAIL.search(s) or PHONE.search(s) for s in [prompt, answer, *choices, *rubric]):
        return None
    return {"type": kind, "prompt": prompt, "choices": choices, "answer": answer,
            "rubric": rubric, "source_id": source_id}


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value) -> list[str] | None:
    """Non-empty stripped strings, or None when the value is not a list of strings."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return [v.strip() for v in value if v.strip()]
