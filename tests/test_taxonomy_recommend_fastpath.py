"""Tests for taxonomy vector caching, batched catalog writes, and recommender fastpaths."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import event

from app.catalog import taxonomy
from app.catalog.taxonomy import (
    encode,
    ensure_taxonomy,
    normalize,
    tag_records,
    tag_resource,
)
from app.llm.embeddings import GeminiEmbeddingEncoder
from app.recommend import Feedback, _title_vector, recommend
from app.vetting import Learner, Node
from assistant.backend.catalog_models import CatalogEmbedding
from assistant.backend.models import Resource


def test_encode_cache_returns_fresh_list_and_reuses_depth3_vectors():
    taxonomy._normalize_cached.cache_clear()
    taxonomy._encode_cached.cache_clear()

    first = encode("Cấu trúc dữ liệu & Giải thuật")
    first[0] = 999.0  # caller mutation must not poison cache
    second = encode("Cấu trúc dữ liệu & Giải thuật")
    assert first != second
    assert taxonomy._encode_cached.cache_info().hits == 1
    assert normalize("Giải thuật") == "giai thuat"

    # First unmatched tag populates _depth3_subject_vectors(); second does not re-encode subjects.
    tag_resource({"title": "zzqxxy unmatched token alpha", "url": "https://x.edu/1"})
    misses_after_first = taxonomy._encode_cached.cache_info().misses
    tag_resource({"title": "zzqxxy unmatched token beta", "url": "https://x.edu/2"})
    misses_after_second = taxonomy._encode_cached.cache_info().misses
    assert misses_after_second - misses_after_first == 1


def test_ensure_taxonomy_and_tag_records_batch_and_scope_embeddings(app, client):
    del client
    class StubSDK:
        def __init__(self):
            self.models = self

        def embed_content(self, **options):
            values = [SimpleNamespace(values=[3.0, 4.0]) for _ in options["contents"]]
            return SimpleNamespace(embeddings=values)

    with app.state.database.sessions() as db:
        resource = Resource(
            url="https://example.edu/scoped-trees",
            canonical_url="https://example.edu/scoped-trees",
            title="Balanced Search Trees",
        )
        db.add(resource)
        # Unrelated node embedding in the same model; must not be scanned by resource tag_records.
        db.add(
            CatalogEmbedding(
                id="unrelated-node-1",
                kind="node",
                model="gemini-embedding-001:default",
                content_hash="deadbeef",
                vector="[0.6, 0.8]",
            )
        )
        db.flush()

        statements: list[str] = []

        def listener(conn, cursor, statement, parameters, context, executemany):
            del conn, cursor, parameters, context, executemany
            statements.append(statement)

        engine = app.state.database.engine
        event.listen(engine, "before_cursor_execute", listener)
        try:
            ensure_taxonomy(db)
            assert (
                tag_records(
                    db,
                    "resource",
                    [{"id": resource.id, "title": resource.title}],
                    embedding=GeminiEmbeddingEncoder(client=StubSDK()),
                )
                == 1
            )
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        unrelated = db.get(CatalogEmbedding, ("unrelated-node-1", "node"))
        assert unrelated is not None
        assert unrelated.model == "gemini-embedding-001:default"

    subject_inserts = [s for s in statements if "INSERT INTO subjects" in s]
    taxonomy_upserts = [
        s for s in statements if "INSERT INTO catalog_embeddings" in s and "'taxonomy'" in s
    ]
    embedding_selects = [s for s in statements if "FROM catalog_embeddings" in s]
    assert len(subject_inserts) == 2  # once from direct call, once inside tag_records
    assert len(taxonomy_upserts) == 1
    assert len(embedding_selects) == 1
    assert "kind IN" in embedding_selects[0] or "id IN" in embedding_selects[0]


def test_recommend_caches_title_vectors_and_preserves_ranking():
    _title_vector.cache_clear()
    node = Node("Binary Search Trees", ("CLO1: balanced search trees",), 45)
    learner = Learner(langs=("en",), level="university")
    database = [
        {
            "kind": "catalog",
            "id": "r1",
            "title": "Binary Search Trees Explained",
            "url": "https://ocw.mit.edu/bst",
            "provider": "mit",
            "institution": "MIT",
            "format": "reading",
            "duration_min": 20,
            "score": 0.92,
            "reason": "matched",
        },
        {
            "kind": "catalog",
            "id": "r2",
            "title": "Unhelpful Lecture Copy",
            "url": "https://example.edu/copy",
            "provider": "web",
            "institution": "Example",
            "format": "video",
            "duration_min": 15,
            "score": 0.90,
            "reason": "matched",
        },
    ]
    feedback = Feedback(rejected=frozenset(), unhelpful_titles=("Unhelpful Lecture Copy",))

    first = recommend(node, learner, feedback=feedback, database=database, external=lambda: ())
    hits_before = _title_vector.cache_info().hits
    second = recommend(node, learner, feedback=feedback, database=database, external=lambda: ())
    hits_after = _title_vector.cache_info().hits

    assert first == second
    assert [r.source_id for r in first] == ["r1", "r2"]
    assert "binary" in first[0].reason.casefold()
    assert hits_after - hits_before >= 3
