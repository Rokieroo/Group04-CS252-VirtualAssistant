"""LLM judge: rubric scores backed by a verbatim quote (spec 11.4, 11.9).

Two safeguards live here.  *Grounded justification*: a quote that is not a
substring of the page text zeroes ``relevance`` and is never returned.
*Prompt injection*: the page sits in a ``<page_text>`` data block, and sentences
that address the grader are removed before the judge ever sees them.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.llm import LLMClient, RetryableError
from app.llm.blocks import BLOCKS
from app.vetting.document import collapse

__all__ = ["FAILED", "JUDGE_PROMPT", "Judgement", "judge", "parse_judgement", "strip_commands"]

log = logging.getLogger("app.vetting.judge")

JUDGE_PROMPT = "judge_v1"
PROMPTS = Path(__file__).parent / "prompts"
MAX_PAGE_CHARS = 12_000  # about 3k tokens: enough to judge, kind to the daily quota
MIN_QUOTE_CHARS = 20  # a word or two matches any page; evidence has to say something
RUBRIC_MAX = 4

SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer", "minimum": 0, "maximum": RUBRIC_MAX},
        "level_fit": {"type": "integer", "minimum": 0, "maximum": RUBRIC_MAX},
        "pedagogy": {"type": "integer", "minimum": 0, "maximum": RUBRIC_MAX},
        "evidence_quote": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["relevance", "level_fit", "pedagogy", "evidence_quote", "reason"],
}

# Defence in depth for spec 11.9: a sentence that talks to the grader is not content.
_COMMAND = re.compile(
    r"""
      \b(?:ignore|disregard|forget|override)\b[^.!?]{0,40}
        \b(?:instructions?|prompts?|rules?|rubric|guidelines?)\b
    | \b(?:rate|score|grade|mark|rank)\b[^.!?]{0,30}
        \b(?:this|the)\s+(?:page|resource|article|document|site|content|text)\b
    | \b(?:you\s+are|act\s+as|pretend\s+to\s+be)\b[^.!?]{0,20}
        \b(?:ai|assistant|model|judge|grader|reviewer|evaluator)\b
    | \bsystem\s+prompt\b
    | \b(?:relevance|level_fit|pedagogy|evidence_quote)\b\s*["']?\s*[:=]
    | \bbỏ\s+qua\b[^.!?]{0,30}\b(?:hướng\s+dẫn|chỉ\s+dẫn|lệnh|yêu\s+cầu|quy\s+tắc)\b
    | \bchấm\b[^.!?]{0,20}\b(?:điểm|trang\s+này|bài\s+này)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_SENTENCE = re.compile(r"[^.!?]+[.!?]*|[.!?]+")


@dataclass(frozen=True)
class Judgement:
    relevance: float  # [0, 1]; already 0 when the quote is not grounded
    level_fit: float
    pedagogy: float
    evidence_quote: str  # a verbatim substring of the page text, or ""
    reason: str


FAILED = Judgement(0.0, 0.0, 0.0, "", "")


def strip_commands(text: str) -> str:
    """``text`` without the sentences that address the grader; otherwise unchanged."""
    return "".join(
        sentence for sentence in _SENTENCE.findall(text) if not _COMMAND.search(sentence)
    ).strip()


def _rubric(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        points = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return min(RUBRIC_MAX, max(0.0, points)) / RUBRIC_MAX


def parse_judgement(answer: str, page_text: str) -> Judgement:
    """Validate the judge's JSON; the quote must appear in ``page_text`` once both have
    their whitespace collapsed (extracted pages keep line breaks, the model's quote does not)."""
    try:
        data = json.loads(answer)
    except (json.JSONDecodeError, TypeError):
        return FAILED
    if not isinstance(data, dict):
        return FAILED
    quote = collapse(str(data.get("evidence_quote") or ""))
    grounded = len(quote) >= MIN_QUOTE_CHARS and quote in collapse(page_text)
    return Judgement(
        relevance=_rubric(data.get("relevance")) if grounded else 0.0,
        level_fit=_rubric(data.get("level_fit")),
        pedagogy=_rubric(data.get("pedagogy")),
        evidence_quote=quote if grounded else "",
        reason=collapse(str(data.get("reason") or ""))[:300],
    )


def _goal(title: str, outcomes: Sequence[str], level: str) -> str:
    lines = [f"Chặng: {title}"]
    lines += [f"CLO: {outcome}" for outcome in outcomes]
    if level:
        lines.append(f"Trình độ người học: {level}")
    return "\n".join(lines)


def judge(
    llm: LLMClient,
    page_text: str,
    *,
    title: str,
    outcomes: Sequence[str] = (),
    level: str = "",
) -> Judgement:
    """Score one page against one node; any LLM failure scores 0 rather than raising."""
    prompt = (
        BLOCKS.wrap("learning_goal", _goal(title, outcomes, level))
        + "\n"
        + BLOCKS.wrap("page_text", strip_commands(page_text)[:MAX_PAGE_CHARS])
    )
    try:
        answer = llm.complete(
            prompt,
            system=(PROMPTS / f"{JUDGE_PROMPT}.txt").read_text(encoding="utf-8"),
            json_schema=SCHEMA,
            max_tokens=1024,
            temperature=0.0,
        ).text
    except (RetryableError, ValueError) as exc:
        log.warning("vetting: judge failed: %s", exc)
        return FAILED
    return parse_judgement(answer, page_text)
