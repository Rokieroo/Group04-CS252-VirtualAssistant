"""Answers to a learner's question at a node, quoted from their pages (issue #163, UC-12).

Spec 12.4: BM25 picks the top-5 pages; when the best one holds too little of the
question the learner is told :data:`NOT_FOUND_MESSAGE` and no model is called; a
citation that does not quote a retrieved page verbatim is dropped. When no model
citation survives (or the model is ``LLM_PROVIDER=fake``), the answer is the best
page's sentence that covers most of the question, a verbatim quote by construction.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm import LLMClient, get_client
from app.llm.blocks import BLOCKS
from app.retrieval import NOT_FOUND_MESSAGE, RetrievalHit, retrieve_top_k, tokenize_vi

log = logging.getLogger("app.qa")
SYSTEM = (Path(__file__).parent / "prompts" / "answer_v1.txt").read_text(encoding="utf-8")
TOP_K = 5
# Share of the question's content words the best page must contain. BM25's
# MIN_SCORE alone lets off-topic questions through (eval/run_retrieval.py).
MIN_COVERAGE = 0.4
SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["source_id", "quote"],
            },
        },
    },
    "required": ["answer", "citations"],
}
# A sentence ends at . ! ? ; followed by a space, or at a line break; "0.9" stays whole.
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\n+")


@dataclass(frozen=True)
class Citation:
    source_id: str
    page: int | None
    quote: str
    file_name: str | None


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[Citation]

    @property
    def found(self) -> bool:
        return bool(self.citations)


NOT_FOUND = Answer(NOT_FOUND_MESSAGE, [])


def _coverage(terms: set[str], text: str) -> float:
    return len(terms & set(tokenize_vi(text))) / len(terms) if terms else 0.0


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _cite(hit: RetrievalHit, quote: str) -> Citation:
    return Citation(hit.source_id, hit.page, quote, hit.file_name)


def _extract(terms: set[str], hit: RetrievalHit) -> Answer:
    """The top page's sentence sharing most words with the question; the first wins ties."""
    sentences = [s.strip() for s in _SENTENCE_END.split(hit.text) if s.strip()]
    sentence = max(sentences, key=lambda s: len(terms & set(tokenize_vi(s))))
    return Answer(sentence, [_cite(hit, sentence)])


def _verified(raw: Any, hits: list[RetrievalHit]) -> list[Citation]:
    """Keep the model's citations that quote a retrieved page verbatim; drop the rest."""
    by_id = {hit.source_id: hit for hit in hits}
    kept = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        hit = by_id.get(str(item.get("source_id") or ""))
        quote = str(item.get("quote") or "").strip()
        # The page comes from retrieval, never from the model.
        if hit and len(quote) >= 5 and _normalized(quote) in _normalized(hit.text):
            kept.append(_cite(hit, quote))
    return kept


def answer_question(
    question: str, pages: Sequence[Any], *, llm: LLMClient | None = None
) -> Answer:
    """Answer ``question`` from ``pages`` (dicts or rows with id, page, file_name, text)."""
    hits = retrieve_top_k(question, pages, top_k=TOP_K)
    terms = set(tokenize_vi(question))
    if not hits or _coverage(terms, hits[0].text) < MIN_COVERAGE:
        return NOT_FOUND
    context = "\n\n".join(
        f"[source_id {hit.source_id}, page {hit.page}, file {hit.file_name}]\n{hit.text}"
        for hit in hits
    )
    try:
        reply = (llm or get_client()).complete(
            f"{BLOCKS.wrap('document_text', context)}\n\nQuestion: {question.strip()}",
            system=SYSTEM,
            json_schema=SCHEMA,
            max_tokens=1024,
            temperature=0.0,
        )
        data = json.loads(reply.text)
    except Exception as exc:  # noqa: BLE001 - the quoted answer below needs no model
        log.warning("qa: model answer unavailable: %s", exc)
        data = {}
    data = data if isinstance(data, dict) else {}
    citations = _verified(data.get("citations"), hits)
    text = str(data.get("answer") or "").strip()
    return Answer(text, citations) if text and citations else _extract(terms, hits[0])
