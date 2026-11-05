"""Exact numbered exercises and offset-only extraction (#115).

No model writes a question, option, answer or rubric. Missing official answers
remain missing; these questions are self-assessed. Whitespace normalization is
the only permitted transformation when checking source evidence.
"""

import hashlib
import re
from uuid import NAMESPACE_URL, uuid5

NUMBER = re.compile(
    r"(?im)^\s*((?:bài(?:\s+tập)?|exercise|problem|question)\s+\d+(?:\.\d+)*[.:)]?|\d+[.)])\s+"
)
ANSWER = re.compile(r"(?im)^\s*(?:answer|đáp án|solution|lời giải)\s*[:.]\s*")
CHOICE = re.compile(r"(?m)^\s*[A-H][.)]\s+")


def collapse(value):
    return re.sub(r"\s+", " ", value).strip()


def quote_hash(prompt, choices=(), answer=None):
    return hashlib.sha256(
        "\x1f".join(
            collapse(s) for s in [prompt or "", *choices, answer or ""]
        ).encode()
    ).hexdigest()


def exact(item, source_text):
    text = collapse(source_text)
    parts = [item.get("prompt"), *(item.get("choices") or []), item.get("answer")]
    return bool(item.get("prompt")) and all(
        isinstance(p, str) and collapse(p) in text for p in parts if p is not None
    )


def from_offsets(source_text, spans):
    """Untrusted extractors may return offsets only; booleans/floats are rejected."""
    result = []
    for span in spans:
        if not isinstance(span, dict) or set(span) - {"start", "end"}:
            continue
        start, end = span.get("start"), span.get("end")
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source_text)
        ):
            continue
        text = source_text[start:end].strip()
        if not NUMBER.match(text):
            continue
        result.extend(extract_numbered(text))
    return result


def extract_numbered(source_text):
    matches = list(NUMBER.finditer(source_text))
    result = []
    for index, match in enumerate(matches):
        end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        )
        block = source_text[match.end() : end].strip()
        if (
            match.group(1)[0].isdigit()
            and "?" not in block
            and not re.search(
                r"(?im)^\s*(?:exercises|problems|bài tập)\s*:?\s*$",
                source_text[: match.start()],
            )
        ):
            continue
        answer = None
        answer_mark = ANSWER.search(block)
        if answer_mark:
            answer = block[answer_mark.end() :].strip() or None
            block = block[: answer_mark.start()].rstrip()
        choice_marks = list(CHOICE.finditer(block))
        choices = [
            block[
                m.end() : choice_marks[i + 1].start()
                if i + 1 < len(choice_marks)
                else len(block)
            ].strip()
            for i, m in enumerate(choice_marks)
        ]
        prompt = block[: choice_marks[0].start()].strip() if choice_marks else block
        item = {
            "type": "mcq" if choices else "short",
            "prompt": prompt,
            "choices": choices,
            "answer": answer,
            "location": match.group(1).strip(),
            "rubric": [],
        }
        if prompt and exact(item, source_text):
            item["quote_hash"] = quote_hash(prompt, choices, answer)
            result.append(item)
    return result


def store_private(db, source, owner_id):
    """Model-free persistence used by HTTP ingest and the legacy FSRS bridge."""
    import json

    from sqlalchemy import text

    owner = db.scalar(text("SELECT owner_id FROM courses WHERE id=:course_id"), source)
    if owner != owner_id:
        raise LookupError("Source not found")
    result = []
    for item in extract_numbered(source["text"]):
        identifier = str(uuid5(NAMESPACE_URL, source["id"] + ":" + item["quote_hash"]))
        if not db.scalar(
            text("SELECT id FROM exercises WHERE id=:id"), {"id": identifier}
        ):
            values = {
                **item,
                "id": identifier,
                "source_id": source["id"],
                "page": source["page"],
                "owner_id": owner_id,
                "source_hash": hashlib.sha256(source["text"].encode()).hexdigest(),
                "choices": json.dumps(item["choices"], ensure_ascii=False),
            }
            db.execute(
                text(
                    "INSERT INTO exercises (id,origin,source_id,page,owner_id,type,prompt,choices,answer,"
                    "location,quote_hash,source_hash,license,difficulty,bloom_level,verification_status) "
                    "VALUES (:id,'user_material',:source_id,:page,:owner_id,:type,:prompt,:choices,:answer,"
                    ":location,:quote_hash,:source_hash,'private',1,'understand','verified')"
                ),
                values,
            )
        result.append({**item, "id": identifier})
    return result
