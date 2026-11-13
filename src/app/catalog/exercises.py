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
PROOF = re.compile(r"(?i)\b(?:prove|show that|chứng minh)\b")
CODE = re.compile(
    r"(?i)\b(?:write|implement|viết|cài đặt)\b.{0,30}\b(?:program|function|code|"
    r"algorithm|chương trình|hàm|thuật toán)\b"
)
NUMERIC = re.compile(r"[-+]?\d+(?:[.,]\d+)?\s*%?")
# Highest level first: "explain and compare" asks for analysis.
BLOOM_VERBS = (
    ("create", r"design|construct|devise|thiết kế|xây dựng"),
    ("evaluate", r"justify|evaluate|critique|assess|prove|đánh giá|biện luận|chứng minh"),
    ("analyze", r"compare|contrast|analy[sz]e|distinguish|so sánh|phân tích|phân biệt"),
    ("apply", r"compute|calculate|solve|apply|implement|trace|convert|write|tính|giải|áp dụng|cài đặt|viết"),
    ("understand", r"explain|describe|summari[sz]e|interpret|why|giải thích|mô tả|trình bày|tại sao"),
)
BLOOM = [(level, re.compile(rf"(?i)\b(?:{verbs})\b")) for level, verbs in BLOOM_VERBS]
BLOOM_RANK = {"remember": 1, "understand": 2, "apply": 3, "analyze": 4, "evaluate": 5, "create": 5}


def collapse(value):
    return re.sub(r"\s+", " ", value).strip()


def classify(prompt, choices=(), answer=None):
    """Type, Bloom level and difficulty read off the source's own wording; no model.

    shortcut: difficulty follows the Bloom level; calibrate it from learners'
    review outcomes once exercises have enough FSRS history.
    """
    if choices:
        kind = "mcq"
    elif PROOF.search(prompt):
        kind = "proof"
    elif CODE.search(prompt):
        kind = "code"
    elif answer and NUMERIC.fullmatch(answer.strip()):
        kind = "numeric"
    else:
        kind = "short"
    bloom = next((level for level, verbs in BLOOM if verbs.search(prompt)), "remember")
    return {"type": kind, "bloom_level": bloom, "difficulty": BLOOM_RANK[bloom]}


def order_for(role, exercises):
    """Practice climbs from easy to hard; a checkpoint takes turns across Bloom
    levels so a short test still samples every kind of thinking the pool has."""
    ranked = sorted(exercises, key=lambda e: (e["difficulty"], e["id"]))
    if role != "checkpoint":
        return ranked
    levels = {}
    for exercise in ranked:
        levels.setdefault(exercise["bloom_level"], []).append(exercise)
    queues = [levels[level] for level in sorted(levels, key=BLOOM_RANK.get)]
    return [q[i] for i in range(max(map(len, queues), default=0)) for q in queues if i < len(q)]


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
            **classify(prompt, choices, answer),
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

    from sqlalchemy import bindparam, text

    owner = db.scalar(text("SELECT owner_id FROM courses WHERE id=:course_id"), source)
    if owner != owner_id:
        raise LookupError("Source not found")

    items = extract_numbered(source["text"])
    if not items:
        return []

    source_hash = hashlib.sha256(source["text"].encode()).hexdigest()
    candidates = [
        (str(uuid5(NAMESPACE_URL, source["id"] + ":" + item["quote_hash"])), item)
        for item in items
    ]
    candidate_ids = list({identifier for identifier, _ in candidates})

    lookup_stmt = text("SELECT id FROM exercises WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    existing: set[str] = set()
    for start in range(0, len(candidate_ids), 500):
        existing.update(
            db.scalars(lookup_stmt, {"ids": candidate_ids[start : start + 500]})
        )

    insert_rows = []
    for identifier, item in candidates:
        if identifier in existing:
            continue
        existing.add(identifier)
        insert_rows.append(
            {
                **item,
                "id": identifier,
                "source_id": source["id"],
                "page": source["page"],
                "owner_id": owner_id,
                "source_hash": source_hash,
                "choices": json.dumps(item["choices"], ensure_ascii=False),
            }
        )

    if insert_rows:
        db.execute(
            text(
                "INSERT INTO exercises (id,origin,source_id,page,owner_id,type,prompt,choices,answer,"
                "location,quote_hash,source_hash,license,difficulty,bloom_level,verification_status) "
                "VALUES (:id,'user_material',:source_id,:page,:owner_id,:type,:prompt,:choices,:answer,"
                ":location,:quote_hash,:source_hash,'private',:difficulty,:bloom_level,'verified')"
            ),
            insert_rows,
        )

    return [{**item, "id": identifier} for identifier, item in candidates]
