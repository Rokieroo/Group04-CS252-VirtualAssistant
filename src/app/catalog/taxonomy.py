"""Bilingual, explainable subject tags with an offline vector fallback (#99).

The bundled encoder hashes lexical features, not an external semantic model.
Callers may inject a semantic encoder; its model name is persisted alongside
vectors so incompatible embeddings are never compared.
"""

import hashlib
import itertools
import json
import logging
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parents[3] / "data/catalog/subjects.yaml"
MODEL = "sha256-word-bigram-256-v1"


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value).casefold()).replace("đ", "d")
    return re.sub(
        r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))
    ).strip()


def encode(value):
    words = normalize(value).split()
    features = words + [a + "_" + b for a, b in itertools.pairwise(words)]
    vector = [0.0] * 256
    for feature in features:
        digest = hashlib.sha256(feature.encode()).digest()
        vector[int.from_bytes(digest[:2], "big") % len(vector)] += (
            1 if digest[2] % 2 else -1
        )
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]


def cosine(left, right):
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


@dataclass(frozen=True)
class Tag:
    subject_id: str
    confidence: float
    method: str

    @property
    def needs_review(self):
        return self.confidence < 0.6


@lru_cache(maxsize=1)
def subjects():
    rows = yaml.safe_load(PATH.read_text(encoding="utf-8"))["subjects"]
    known = set()
    for row in rows:
        if row["id"] in known or (
            row.get("parent_id") and row["parent_id"] not in known
        ):
            raise ValueError("invalid_taxonomy_tree")
        known.add(row["id"])
    return rows


def _tags(title, context="", *, encoder=encode, semantic=False):
    title_key, context_key = (
        " " + normalize(title) + " ",
        " " + normalize(context) + " ",
    )
    matches = []
    for row in subjects():
        terms = [row["name"], row["name_vi"], *row.get("aliases", [])]
        if any(" " + normalize(term) + " " in title_key for term in terms if term):
            matches.append(Tag(row["id"], 0.95, "rule:title"))
    if matches:
        # Prefer a concrete topic over its ancestor if both phrases matched.
        parents = {
            r.get("parent_id")
            for r in subjects()
            if any(t.subject_id == r["id"] for t in matches)
        }
        return [t for t in matches if t.subject_id not in parents][:5]
    course = [
        Tag(r["id"], 0.65, "rule:course")
        for r in subjects()
        if r.get("depth") == 2
        and any(
            " " + normalize(term) + " " in context_key
            for term in [r["name"], r["name_vi"], *r.get("aliases", [])]
        )
    ]
    if course:
        return course[:2]
    vector = encoder(title + " " + context)
    ranked = sorted(
        (
            (
                cosine(
                    vector,
                    encoder(" ".join([r["name"], r["name_vi"], *r.get("aliases", [])])),
                ),
                r["id"],
            )
            for r in subjects()
            if r.get("depth") == 3
        ),
        reverse=True,
    )
    if ranked and ranked[0][0] > 0.12:
        score, identifier = ranked[0]
        confidence = min(0.9 if semantic else 0.59, max(0.2, score))
        return [
            Tag(
                identifier, confidence, "embedding" if semantic else "lexical_embedding"
            )
        ]
    return [Tag("computing", 0.3, "unclassified:review")]


def tag_node(node, *, course="", outcomes=(), encoder=encode, semantic=False):
    title = node.get("title", "") if isinstance(node, Mapping) else node.title
    return _tags(
        title, " ".join([course, *outcomes]), encoder=encoder, semantic=semantic
    )


def tag_resource(resource, *, encoder=encode, semantic=False):
    get = (
        resource.get
        if isinstance(resource, Mapping)
        else lambda k, d="": getattr(resource, k, d)
    )
    return _tags(
        get("title", ""),
        " ".join(
            str(get(k, "") or "")
            for k in ("code", "course", "department", "description")
        ),
        encoder=encoder,
        semantic=semantic,
    )


def ensure_taxonomy(db):
    """Seed stable labels atomically when concurrent workers see an empty catalog."""
    from sqlalchemy import text

    for row in subjects():
        db.execute(
            text(
                "INSERT INTO subjects (id,parent_id,slug,name,name_vi) "
                "VALUES (:id,:parent_id,:slug,:name,:name_vi) ON CONFLICT(id) DO NOTHING"
            ),
            {"parent_id": None, **row, "slug": row["id"]},
        )


def save_tags(
    db, kind, identifier, tags, content, *, vector=None, model=MODEL, ensure=True
):
    """Replace machine tags atomically; preserve manually reviewed tags."""
    from sqlalchemy import text

    if kind not in {"node", "resource"}:
        raise ValueError("unknown_tag_kind")
    if ensure:
        ensure_taxonomy(db)
    table, key = (
        ("node_subjects", "node_id")
        if kind == "node"
        else ("resource_subjects", "resource_id")
    )
    db.execute(
        text(f"DELETE FROM {table} WHERE {key}=:id AND method <> 'manual'"),
        {"id": identifier},
    )
    for tag in tags:
        values = {
            "id": identifier,
            "subject": tag.subject_id,
            "confidence": tag.confidence,
            "method": tag.method,
        }
        db.execute(
            text(
                f"INSERT INTO {table} ({key},subject_id,confidence,method) "
                "VALUES (:id,:subject,:confidence,:method) "
                f"ON CONFLICT({key},subject_id) DO UPDATE SET confidence=excluded.confidence, "
                f"method=excluded.method WHERE {table}.method <> 'manual'"
            ),
            values,
        )
    params = {
        "id": identifier,
        "kind": kind,
        "model": model,
        "node_id": identifier if kind == "node" else None,
        "resource_id": identifier if kind == "resource" else None,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "vector": json.dumps(vector if vector is not None else encode(content)),
    }
    db.execute(
        text(
            "INSERT INTO catalog_embeddings (id,kind,model,content_hash,vector,node_id,resource_id) "
            "VALUES (:id,:kind,:model,:content_hash,:vector,:node_id,:resource_id) "
            "ON CONFLICT(id,kind) DO UPDATE SET model=excluded.model, content_hash=excluded.content_hash, "
            "vector=excluded.vector, node_id=excluded.node_id, resource_id=excluded.resource_id"
        ),
        params,
    )


def tag_records(db, kind, records, *, embedding=None):
    """Batch semantic encoding on explicit writes; reuse model/hash-matched vectors.

    Connectors may call this for resources; roadmap generation calls it for nodes.
    The shared vocabulary is public; node vectors retain their node FK and privacy.
    Vendor errors fall back to lexical rules/vectors without logging uploaded text.
    """
    from sqlalchemy import text

    from app.llm.embeddings import clean

    if kind not in {"node", "resource"}:
        raise ValueError("unknown_tag_kind")
    records = list(records)
    if not records:
        return 0
    contents = []
    for row in records:
        context = (
            " ".join([row.get("course", ""), *row.get("outcomes", [])])
            if kind == "node"
            else " ".join(
                str(row.get(k, "") or "")
                for k in ("code", "course", "department", "description")
            )
        )
        contents.append(clean(row["title"] + " " + context))
    vocabulary = {
        r["id"]: clean(" ".join([r["name"], r["name_vi"], *r.get("aliases", [])]))
        for r in subjects()
        if r.get("depth") == 3
    }
    if embedding is not None:
        cached = db.execute(
            text(
                "SELECT id,kind,model,content_hash,vector FROM catalog_embeddings "
                "WHERE model=:model"
            ),
            {"model": embedding.model},
        ).mappings()
        wanted = {
            (r["id"], kind): value for r, value in zip(records, contents, strict=True)
        }
        wanted.update({(key, "taxonomy"): value for key, value in vocabulary.items()})
        for row in cached:
            value = wanted.get((row["id"], row["kind"]))
            if (
                value
                and hashlib.sha256(value.encode()).hexdigest() == row["content_hash"]
            ):
                embedding.cache[value] = json.loads(row["vector"])
        try:
            embedding.prepare([*vocabulary.values(), *contents])
        except (ValueError, RuntimeError, ImportError) as exc:
            logging.getLogger(__name__).warning(
                "embedding_unavailable error=%s", type(exc).__name__
            )
            embedding = None
    if embedding is not None:
        for identifier, value in vocabulary.items():
            params = {
                "id": identifier,
                "model": embedding.model,
                "hash": hashlib.sha256(value.encode()).hexdigest(),
                "vector": json.dumps(embedding.encode(value)),
            }
            db.execute(
                text(
                    "INSERT INTO catalog_embeddings (id,kind,model,content_hash,vector) "
                    "VALUES (:id,'taxonomy',:model,:hash,:vector) "
                    "ON CONFLICT(id,kind) DO UPDATE SET model=excluded.model, "
                    "content_hash=excluded.content_hash, vector=excluded.vector"
                ),
                params,
            )
    ensure_taxonomy(db)
    for row, content in zip(records, contents, strict=True):
        encoder = embedding.encode if embedding else encode
        tags = (
            tag_node(
                row,
                course=row.get("course", ""),
                outcomes=row.get("outcomes", []),
                encoder=encoder,
                semantic=embedding is not None,
            )
            if kind == "node"
            else tag_resource(row, encoder=encoder, semantic=embedding is not None)
        )
        save_tags(
            db,
            kind,
            row["id"],
            tags,
            content,
            vector=encoder(content),
            model=embedding.model if embedding else MODEL,
            ensure=False,
        )
    return len(records)
