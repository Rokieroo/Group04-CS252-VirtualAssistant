"""Visual pass over a PDF (issue #9): a vision model notes what text extraction misses.

Diagrams, charts, image tables and scanned pages carry ideas that pypdf cannot read. The
notes are stored beside each page's text and read by concept extraction; they are never
cited, because they are model output, not the slide's own words. Given earlier notes (a
re-upload), the model revises them instead of starting over.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.llm import LLMClient
from app.llm.blocks import BLOCKS

log = logging.getLogger("app.concepts")

PROMPT = Path(__file__).parent / "prompts" / "visual_v1.txt"
PAGES_PER_CALL = 20  # small enough that the model looks at every page closely
PARALLEL = 4  # chunks in flight at once; chunks never share a page
MAX_NOTE = 1200
MAX_INLINE_BYTES = 14 * 1024 * 1024  # Gemini's 20 MB request limit counts base64 overhead
SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"page": {"type": "integer"}, "notes": {"type": "string"}},
                "required": ["page", "notes"],
            },
        }
    },
    "required": ["pages"],
}


def read_visuals(llm: LLMClient, pdf: bytes, page_count: int,
                 previous: list[str] | None = None) -> list[str]:
    """One note per page, "" when a page shows nothing beyond its text. Never raises.

    ``previous`` holds notes from an earlier upload of this file; a chunk whose call fails
    keeps them.
    """
    previous = previous or [""] * page_count
    system = PROMPT.read_text(encoding="utf-8")

    def chunk_notes(first: int) -> list[str]:
        last = min(first + PAGES_PER_CALL, page_count)
        earlier = previous[first:last]
        # Optional enrichment: any failure (quota, bad JSON, oversized or odd PDF) only costs
        # these pages their new notes, never the upload.
        try:
            chunk = pdf if (first, last) == (0, page_count) else _pages(pdf, first, last)
            if len(chunk) > MAX_INLINE_BYTES:
                raise ValueError(f"{len(chunk)} bytes is over the inline limit")
            prompt = f"The attached PDF has {last - first} pages, numbered 1-{last - first}."
            if any(earlier):
                listing = "\n".join(f"[Page {n}]\n{note}"
                                    for n, note in enumerate(earlier, start=1) if note)
                prompt += "\n" + BLOCKS.wrap("previous_notes", listing)
            answer = llm.complete(prompt, system=system, json_schema=SCHEMA, max_tokens=8192,
                                  temperature=0.2, pdf=chunk).text
            notes = [""] * (last - first)
            for item in json.loads(answer)["pages"]:
                number = item.get("page")
                if type(number) is int and 1 <= number <= last - first:
                    notes[number - 1] = str(item.get("notes") or "").strip()[:MAX_NOTE]
            return notes
        except Exception as exc:  # noqa: BLE001
            log.warning("visuals: skipped pages %d-%d: %s", first + 1, last, exc)
            return earlier

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        chunks = pool.map(chunk_notes, range(0, page_count, PAGES_PER_CALL))
        return [note for notes in chunks for note in notes]


def _pages(pdf: bytes, first: int, last: int) -> bytes:
    """Pages first+1..last (1-based) as their own PDF."""
    writer = PdfWriter()
    for page in PdfReader(BytesIO(pdf)).pages[first:last]:
        writer.add_page(page)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
