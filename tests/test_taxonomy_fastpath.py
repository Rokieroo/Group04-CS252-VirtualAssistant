"""The vector fallback compares against every topic label; tag_records reads only its own vectors."""

from types import SimpleNamespace

from sqlalchemy import event

from app.catalog.taxonomy import (
    _topic_labels,
    cosine,
    encode,
    tag_records,
    tag_resource,
)
from app.llm.embeddings import GeminiEmbeddingEncoder
from assistant.backend.catalog_models import CatalogEmbedding
from assistant.backend.models import Resource


def test_lexical_fallback_picks_the_closest_topic_label():
    title = "qwerty pointers allocation"  # names no label, so only vectors decide
    vector = encode(title)
    expected = max(
        (cosine(vector, encode(label)), i) for i, label in _topic_labels().items()
    )

    for _ in range(2):  # the second call reads the label vectors built by the first
        (tag,) = tag_resource({"title": title})
        assert (tag.subject_id, tag.method) == (expected[1], "lexical_embedding")


def test_injected_encoder_still_encodes_the_labels():
    target = next(iter(_topic_labels()))

    def encoder(value):
        hit = value.startswith("qwerty") or value == _topic_labels()[target]
        return [1.0, 0.0] if hit else [0.0, 1.0]

    (tag,) = tag_resource({"title": "qwerty"}, encoder=encoder, semantic=True)
    assert (tag.subject_id, tag.method) == (target, "embedding")


def test_tag_records_looks_up_only_this_batch_and_the_labels(app, client):
    del client

    class StubSDK:
        models = property(lambda self: self)

        def embed_content(self, **options):
            return SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[3.0, 4.0]) for _ in options["contents"]
                ]
            )

    with app.state.database.sessions() as db:
        resource = Resource(
            url="https://example.edu/scoped-trees",
            canonical_url="https://example.edu/scoped-trees",
            title="Balanced Search Trees",
        )
        db.add(resource)
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
        engine = app.state.database.engine

        def capture(conn, cursor, statement, *_):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            records = [{"id": resource.id, "title": resource.title}]
            embedding = GeminiEmbeddingEncoder(client=StubSDK())
            assert tag_records(db, "resource", records, embedding=embedding) == 1
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert (
            db.get(CatalogEmbedding, ("unrelated-node-1", "node")).vector
            == "[0.6, 0.8]"
        )
        stored = db.get(CatalogEmbedding, (resource.id, "resource"))
        assert stored.model == embedding.model

    lookups = [
        s
        for s in statements
        if s.lstrip().startswith("SELECT") and "catalog_embeddings" in s
    ]
    assert lookups and all("id IN" in s for s in lookups)
