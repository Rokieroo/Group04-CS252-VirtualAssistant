"""LLM step of #114: one call reads the outline of a file and splits it into sections,
each assigned to the roadmap node it teaches.

The model sees each page's opening words only, which is what a person skims to find
the sections of a deck. Nodes are referred to by short keys the schema enumerates,
and every answer is validated: an unknown key, a page outside the window or a
malformed segment is dropped, and any failure leaves the deterministic matches as
they were.
"""

import json
import logging
from pathlib import Path

from app.llm import LLMClient, RetryableError
from app.llm.blocks import BLOCKS
from app.materials.mapping import PageMatch

log = logging.getLogger(__name__)

PROMPT = Path(__file__).parent / "prompts" / "segment_v1.txt"
OUTLINE_CHARS = 160  # a page's heading and first words
WINDOW = 250  # pages per call: a deck takes one call, a textbook a few
LLM_CAP = 0.85  # a model's self-reported certainty is weaker evidence than a person's
NONE = "none"


def segment(llm: LLMClient, pages: list[str], nodes) -> dict[int, PageMatch | None]:
    """Page number -> the model's match, or None where it says the page teaches no node.

    Pages the model did not cover (or every page, when the call fails) are absent.
    """
    keys = {f"N{i}": node for i, node in enumerate(nodes, 1)}
    decisions: dict[int, PageMatch | None] = {}
    for first in range(0, len(pages), WINDOW):
        last = min(first + WINDOW, len(pages))
        decisions.update(_window(llm, pages, first, last, keys))
    return decisions


def _excerpt(text: str) -> str:
    return " / ".join(line.strip() for line in text.splitlines() if line.strip())[
        :OUTLINE_CHARS
    ] or "(no text)"


def _window(llm, pages, first, last, keys) -> dict[int, PageMatch | None]:
    prompt = (
        BLOCKS.wrap("roadmap_nodes", "\n".join(f"{k}: {n.title}" for k, n in keys.items()))
        + "\n"
        + BLOCKS.wrap(
            "material_outline",
            "\n".join(f"{n}: {_excerpt(pages[n - 1])}" for n in range(first + 1, last + 1)),
        )
    )
    schema = {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "page_from": {"type": "integer"},
                        "page_to": {"type": "integer"},
                        "node": {"type": "string", "enum": [*keys, NONE]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["page_from", "page_to", "node", "confidence"],
                },
            }
        },
        "required": ["segments"],
    }
    try:
        answer = llm.complete(
            prompt,
            system=PROMPT.read_text(encoding="utf-8"),
            json_schema=schema,
            max_tokens=4096,
            temperature=0.0,
        ).text
        segments = json.loads(answer)["segments"]
        if not isinstance(segments, list):
            raise TypeError("segments")
    except (RetryableError, ValueError, TypeError, KeyError) as exc:
        log.warning("material_segment_failed error=%s", type(exc).__name__)
        return {}
    decisions: dict[int, PageMatch | None] = {}
    for row in segments:
        parsed = _segment(row, first, last, keys)
        if parsed is None:
            continue
        start, end, node, confidence = parsed
        for number in range(start, end + 1):
            # The first segment covering a page wins; overlaps never reassign it.
            decisions.setdefault(
                number,
                None if node is None else PageMatch(number, node.id, confidence, "llm"),
            )
    return decisions


def _segment(row, first, last, keys):
    """(page_from, page_to, node or None, confidence), or None for an invalid segment."""
    try:
        start, end = row["page_from"], row["page_to"]
        key, confidence = row["node"], row["confidence"]
    except (KeyError, TypeError):
        return None
    if not all(type(v) is int for v in (start, end)) or not first < start <= end <= last:
        return None
    if key != NONE and key not in keys:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return None
    confidence = round(min(LLM_CAP, max(0.0, float(confidence))), 3)
    return start, end, None if key == NONE else keys[key], confidence
