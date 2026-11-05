"""Semantic embeddings remain opt-in; test model isolation, batching and fallback offline."""

from types import SimpleNamespace

import httpx
import pytest

from app.catalog.taxonomy import MODEL, tag_records
from app.llm.embeddings import GeminiEmbeddingEncoder, get_embedding_encoder
from assistant.backend.catalog_models import CatalogEmbedding, ResourceSubject
from assistant.backend.models import Resource


class SDK:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.models = self

    def embed_content(self, **options):
        self.calls.append(options)
        if self.fail:
            raise httpx.ReadTimeout("private provider detail")
        values = [SimpleNamespace(values=[3.0, 4.0]) for value in options["contents"]]
        return SimpleNamespace(embeddings=values)


def test_encoder_batches_and_normalizes_without_aggregation():
    sdk = SDK()
    encoder = GeminiEmbeddingEncoder(client=sdk)
    encoder.prepare([f"text {i}" for i in range(205)])
    assert [len(c["contents"]) for c in sdk.calls] == [100, 100, 5]
    assert all(c["model"] == "gemini-embedding-001" for c in sdk.calls)
    assert encoder.encode("text   0") == [0.6, 0.8]
    encoder.prepare(["text 0"])
    assert len(sdk.calls) == 3


@pytest.mark.parametrize(
    "vectors", [[], [[float("nan"), 1]], [[0, 0]], [[1, 0], [1, 0]]]
)
def test_encoder_rejects_invalid_or_aggregated_responses(vectors):
    sdk = SimpleNamespace(
        models=SimpleNamespace(
            embed_content=lambda **kwargs: SimpleNamespace(
                embeddings=[SimpleNamespace(values=value) for value in vectors]
            )
        )
    )
    with pytest.raises(ValueError):
        GeminiEmbeddingEncoder(client=sdk).prepare(["one input"])


def test_encoder_is_opt_in_even_when_key_exists(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-placeholder")
    monkeypatch.setenv("EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert get_embedding_encoder() is None
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(get_embedding_encoder(), GeminiEmbeddingEncoder)
    monkeypatch.setenv("EMBEDDING_MODEL", "gemini-embedding-2")
    assert get_embedding_encoder() is None


def test_tag_records_reuses_persisted_semantic_vectors(app, client, headers):
    with app.state.database.sessions() as db:
        resource = Resource(
            url="https://example.edu/notes",
            canonical_url="https://example.edu/notes",
            title="Solution ladder",
        )
        db.add(resource)
        db.flush()
        records = [{"id": resource.id, "title": resource.title}]
        first = SDK()
        assert (
            tag_records(
                db, "resource", records, embedding=GeminiEmbeddingEncoder(client=first)
            )
            == 1
        )
        db.commit()
        assert len(first.calls) == 1
        vector = db.get(CatalogEmbedding, (resource.id, "resource"))
        assert vector.model.startswith("gemini-embedding-001")
        assert db.get(ResourceSubject, (resource.id, "ct.ladder")).confidence == 0.95
        second = SDK()
        tag_records(
            db, "resource", records, embedding=GeminiEmbeddingEncoder(client=second)
        )
        assert second.calls == []


def test_embedding_provider_error_falls_back_without_logging_content(
    app, client, headers, caplog
):
    with app.state.database.sessions() as db:
        resource = Resource(
            url="https://example.edu/fallback",
            canonical_url="https://example.edu/fallback",
            title="Private title",
        )
        db.add(resource)
        db.flush()
        tag_records(
            db,
            "resource",
            [{"id": resource.id, "title": resource.title}],
            embedding=GeminiEmbeddingEncoder(client=SDK(fail=True)),
        )
        assert db.get(CatalogEmbedding, (resource.id, "resource")).model == MODEL
        assert "private provider detail" not in caplog.text
        assert "Private title" not in caplog.text
        assert "embedding_unavailable" in caplog.text


def test_ranker_does_not_compare_vectors_from_different_models():
    from app.catalog.matching import match_sources

    node = {
        "title": "Anonymous topic",
        "subjects": ["ct.ladder"],
        "language": "en",
        "level": "undergrad",
        "vector": [1, 0],
        "vector_model": "model-A",
    }
    resource = {
        "id": "r",
        "title": "Solution ladder",
        "subjects": ["ct.ladder"],
        "lang": "en",
        "level": "undergrad",
        "domain": "example.edu",
        "format": "reading",
        "tier": 1,
        "is_free": True,
        "verification_status": "verified",
        "vector": [1, 0],
        "vector_model": "model-B",
    }
    mismatch = match_sources(node, [resource])[0]["score"]
    baseline = match_sources({**node, "vector": None}, [{**resource, "vector": None}])[
        0
    ]["score"]
    assert mismatch == baseline


def test_roadmap_embedding_is_batched_and_source_get_does_not_call_provider(
    app, client, headers, monkeypatch
):
    from assistant.backend import catalog_repository

    sdk = SDK()
    monkeypatch.setattr(
        catalog_repository,
        "get_embedding_encoder",
        lambda: GeminiEmbeddingEncoder(client=sdk),
    )
    course = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014"}
    ).json()["id"]
    result = client.post(
        f"/api/v1/courses/{course}/roadmap:generate",
        headers=headers,
        json={
            "nodes": [
                {"title": "Solution ladder", "week": 1},
                {"title": "Use case", "week": 2},
            ]
        },
    )
    assert result.status_code == 201, result.text
    assert len(sdk.calls) == 1
    node = result.json()["nodes"][0]["id"]
    with app.state.database.sessions() as db:
        assert db.get(CatalogEmbedding, (node, "node")).model.startswith(
            "gemini-embedding-001"
        )
    assert (
        client.get(f"/api/v1/concepts/{node}/sources", headers=headers).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/roadmaps/{result.json()['id']}/sources:summary", headers=headers
        ).status_code
        == 200
    )
    assert len(sdk.calls) == 1


def test_embedding_dimension_cannot_change_between_batches():
    class ChangingSDK(SDK):
        def embed_content(self, **options):
            self.calls.append(options)
            dimension = 2 if len(self.calls) == 1 else 3
            return SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[1.0] * dimension)
                    for _ in options["contents"]
                ]
            )

    with pytest.raises(ValueError, match="inconsistent_embedding_dimensions"):
        GeminiEmbeddingEncoder(client=ChangingSDK()).prepare(
            [f"text {i}" for i in range(101)]
        )


@pytest.mark.parametrize("semantic", [False, True])
def test_concurrent_taggers_share_taxonomy_and_embedding_cache(
    tmp_path, database_url, semantic
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import func, select

    from app.catalog.taxonomy import subjects
    from assistant.backend.database import Database
    from assistant.backend.models import Subject

    database = Database(
        "sqlite:///" + (tmp_path / "tags.db").as_posix()
        if database_url == "sqlite://"
        else database_url
    )
    database.create_schema()
    with database.sessions() as db:
        resources = [
            Resource(
                url=f"https://example.edu/{i}",
                canonical_url=f"https://example.edu/{i}",
                title="Solution ladder",
            )
            for i in range(2)
        ]
        db.add_all(resources)
        db.commit()
        identifiers = [row.id for row in resources]
    start = Barrier(2)

    def tag(identifier):
        with database.sessions() as db:
            start.wait(timeout=10)
            tag_records(
                db,
                "resource",
                [{"id": identifier, "title": "Solution ladder"}],
                embedding=GeminiEmbeddingEncoder(client=SDK()) if semantic else None,
            )
            db.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        runs = [executor.submit(tag, identifier) for identifier in identifiers]
        for result in runs:
            result.result(timeout=20)
    with database.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Subject)) == len(subjects())
        assert db.scalar(select(func.count()).select_from(ResourceSubject)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(CatalogEmbedding)
                .where(CatalogEmbedding.kind == "resource")
            )
            == 2
        )
        if semantic:
            assert db.scalar(
                select(func.count())
                .select_from(CatalogEmbedding)
                .where(CatalogEmbedding.kind == "taxonomy")
            ) == len([r for r in subjects() if r["depth"] == 3])
    database.engine.dispose()
