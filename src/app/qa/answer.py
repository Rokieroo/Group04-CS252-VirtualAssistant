"""Question answering with verbatim citations over node materials (issue #163, UC-12).

Uses BM25 retrieval to find relevant slide pages, prompts the LLM to answer using
only those pages with exact quotes, and enforces verify-or-drop citation validation.
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
from app.retrieval import (
    MIN_SCORE,
    NOT_FOUND_MESSAGE,
    RetrievalHit,
    retrieve_top_k,
    tokenize_vi,
)

log = logging.getLogger("app.qa")
PROMPTS = Path(__file__).parent / "prompts"
ANSWER_PROMPT = "answer_v1"

_PRIVACY_PATTERNS = [
    re.compile(r"\b(?:email|điểm|gpa|kết quả|bài làm)\b.*\b(?:bạn|sinh viên|người khác|user_[a-z0-9]+)\b", re.IGNORECASE),
    re.compile(r"\b(?:mật khẩu|password|token|tài khoản)\b.*\b(?:bạn|sinh viên|người khác|user_[a-z0-9]+)\b", re.IGNORECASE),
    re.compile(r"\bcho (?:mình|em|tôi) (?:xin|xem|biết) (?:email|điểm|thông tin cá nhân)\b", re.IGNORECASE),
]


@dataclass
class Citation:
    source_id: str
    page: int
    quote: str
    file_name: str | None = None


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]
    found: bool
    suggested_sources: list[dict[str, Any]]


def is_privacy_query(question: str) -> bool:
    """Return True if the question attempts to access another user's private data or PII."""
    q = question.strip()
    return any(p.search(q) for p in _PRIVACY_PATTERNS)


def _clean(text: str) -> str:
    return " ".join(text.split()).casefold()


def _is_verbatim(quote: str, source_text: str) -> bool:
    """Check if ``quote`` appears verbatim in ``source_text`` ignoring case and extra whitespace."""
    if not quote or not source_text:
        return False
    q_clean = _clean(quote)
    s_clean = _clean(source_text)
    return len(q_clean) >= 5 and q_clean in s_clean


_STRUCTURAL_WORDS = frozenset(
    {
        "trong", "theo", "slide", "slides", "của", "và", "là", "gì", "nào", "những",
        "các", "một", "có", "cho", "được", "với", "thế", "ở", "đâu", "lại", "sao",
        "như", "khi", "để", "này", "đó", "môn", "phần", "gồm", "bao", "nhiêu", "thứ",
        "bài", "mình", "xin", "xem", "hỏi", "sinh", "câu", "luyện", "tập",
        "hoạt", "động", "phát", "biểu", "nêu", "thể", "hiện", "chính", "trước",
        "chuẩn", "chia", "thành", "bước",
    }
)


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def _fallback_extract(top_hit: RetrievalHit, question: str) -> tuple[str, list[Citation]]:
    """Deterministic offline answer extraction directly from the top retrieved snippet."""
    text = (top_hit.text or "").strip()
    if not text:
        return NOT_FOUND_MESSAGE, []

    # Check query content grounding
    q_tokens = [w for w in tokenize_vi(question) if w not in _STRUCTURAL_WORDS]
    doc_tokens = set(tokenize_vi(text))
    matched = [w for w in q_tokens if w in doc_tokens]

    if not q_tokens or not matched:
        return NOT_FOUND_MESSAGE, []
    if (len(matched) / len(q_tokens)) < 0.40:
        return NOT_FOUND_MESSAGE, []

    sentences = [s.strip() for s in re.split(r"[.\n;]", text) if len(s.strip()) > 10]
    sentence = sentences[0] if sentences else text
    citation = Citation(
        source_id=top_hit.source_id,
        page=top_hit.page or 1,
        quote=sentence,
        file_name=top_hit.file_name,
    )
    return sentence, [citation]


def answer_node_question(
    question: str,
    sources: Sequence[Any],
    *,
    llm: LLMClient | None = None,
    min_score: float = MIN_SCORE,
    suggested_sources: list[dict[str, Any]] | None = None,
) -> AnswerResult:
    """Answer a learner question at a node, enforcing verbatim citations (UC-12).

    1. Checks privacy and refuses personal information requests.
    2. BM25 retrieves top-5 pages; if below ``min_score``, returns 'not found'
       with suggested sources and never invokes the model.
    3. Calls LLM with retrieved snippets and validates citations verbatim (verify-or-drop).
    """
    suggested = suggested_sources or []

    # 1. Privacy safeguard
    if is_privacy_query(question):
        return AnswerResult(
            answer="Từ chối: Hệ thống không tiết lộ thông tin cá nhân hoặc kết quả học tập của người khác.",
            citations=[],
            found=False,
            suggested_sources=[],
        )

    # 2. Retrieval step
    effective_min = 0.5 if (len(sources) < 3 and min_score == MIN_SCORE) else min_score
    hits = retrieve_top_k(question, sources, top_k=5, min_score=effective_min)
    if not hits:
        return AnswerResult(
            answer=NOT_FOUND_MESSAGE,
            citations=[],
            found=False,
            suggested_sources=suggested,
        )

    client = llm if llm is not None else get_client()

    # Build context for LLM
    context_blocks = []
    hit_by_id: dict[str, RetrievalHit] = {}
    for hit in hits:
        hit_by_id[hit.source_id] = hit
        context_blocks.append(
            f"[Source {hit.source_id}, Page {hit.page or 1}, File {hit.file_name or 'doc'}]:\n{hit.text or ''}"
        )
    context_str = "\n\n".join(context_blocks)

    prompt_body = (
        f"{BLOCKS.wrap('document_text', context_str)}\n\n"
        f"Question: {question.strip()}"
    )

    answer_text = ""
    raw_citations: list[dict[str, Any]] = []

    try:
        response = client.complete(
            prompt_body,
            system=_prompt(ANSWER_PROMPT),
            max_tokens=1024,
            temperature=0.0,
        )
        data = json.loads(response.text)
        if isinstance(data, dict):
            answer_text = str(data.get("answer") or "").strip()
            raw_citations = data.get("citations", [])
    except Exception as exc:  # noqa: BLE001
        log.debug("qa: LLM response parsing failed or offline fallback: %s", exc)

    # If LLM gave no usable output (e.g. empty FakeLLM response in offline mode), use top hit
    if not answer_text or not raw_citations:
        answer_text, verified_citations = _fallback_extract(hits[0], question)
        if not verified_citations:
            return AnswerResult(
                answer=NOT_FOUND_MESSAGE,
                citations=[],
                found=False,
                suggested_sources=suggested,
            )
        return AnswerResult(
            answer=answer_text,
            citations=verified_citations,
            found=True,
            suggested_sources=[],
        )

    # 3. Verify-or-drop citations
    verified_citations: list[Citation] = []
    for c in raw_citations:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("source_id") or "").strip()
        page = c.get("page")
        quote = str(c.get("quote") or "").strip()
        hit = hit_by_id.get(sid)
        if not hit or not _is_verbatim(quote, hit.text or ""):
            continue  # Drop ungrounded citation
        verified_citations.append(
            Citation(
                source_id=sid,
                page=int(page) if page is not None else (hit.page or 1),
                quote=quote,
                file_name=hit.file_name,
            )
        )

    if not verified_citations:
        # None of the citations survived verification: fallback to top hit excerpt
        answer_text, verified_citations = _fallback_extract(hits[0])

    return AnswerResult(
        answer=answer_text,
        citations=verified_citations,
        found=True,
        suggested_sources=[],
    )
