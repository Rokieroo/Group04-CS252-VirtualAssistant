"""Ingest boundaries use real PDF bytes and an isolated application database."""
from io import BytesIO

import jwt
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import text

from app.db import get_engine


def pdf_bytes(texts=("Solution ladder", "")):
    writer = PdfWriter()
    for value in texts:
        page = writer.add_blank_page(width=300, height=300)
        if value:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
            })
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 10 100 Td ({value}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


@pytest.fixture
def study(tmp_path, monkeypatch):
    from app.api.main import create_app

    secret = "test-secret-with-at-least-thirty-two-bytes"
    monkeypatch.setenv("JWT_SECRET", secret)
    url = f"sqlite:///{(tmp_path / 'study.db').as_posix()}"
    app = create_app(url)
    with TestClient(app) as client:
        with get_engine(url).begin() as connection:
            for user in ("alice", "bob"):
                connection.execute(text(
                    "INSERT INTO users (id,email,password_hash) VALUES (:id,:email,'test')"
                ), {"id": user, "email": f"{user}@example.com"})
        headers = {"Authorization": "Bearer " + jwt.encode(
            {"sub": "alice", "exp": 4102444800}, secret, algorithm="HS256"
        )}
        yield client, headers, app, url
    get_engine(url).dispose()


def course(study):
    client, headers, _, _ = study
    response = client.post("/api/v1/courses", headers=headers, json={"title": "CS252"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(study, course_id, data=None, name="slides.pdf"):
    client, headers, _, _ = study
    return client.post(f"/api/v1/courses/{course_id}/sources", headers=headers,
                       files={"file": (name, pdf_bytes() if data is None else data, "application/pdf")})


def test_ingest_preserves_page_numbers_and_text(study):
    client, headers, _, _ = study
    course_id = course(study)
    response = upload(study, course_id)
    assert response.status_code == 201, response.text
    assert response.json()["pages"] == 2
    rows = client.get(f"/api/v1/courses/{course_id}/sources", headers=headers).json()["sources"]
    assert [row["page"] for row in rows] == [1, 2]
    assert "Solution ladder" in rows[0]["text"]
    assert rows[1]["text"] == ""
    assert upload(study, course_id).status_code == 409
    assert len(client.get(f"/api/v1/courses/{course_id}/sources", headers=headers).json()["sources"]) == 2


@pytest.mark.parametrize("name,data,status,code", [
    ("slides.txt", b"%PDF-1.4", 415, "not_pdf"),
    ("slides.pdf", b"not a PDF", 415, "not_pdf"),
    ("slides.pdf", b"%PDF-broken", 400, "invalid_pdf"),
    ("slides.pdf", b"%PDF" + b"x" * (20 * 1024 * 1024), 413, "file_too_large"),
])
def test_invalid_uploads(study, name, data, status, code):
    response = upload(study, course(study), data, name)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_scanned_warning(study):
    response = upload(study, course(study), pdf_bytes(("", "", "", "", "")))
    assert response.json()["warnings"] == ["scanned_pdf"]


def test_auth_and_owner_scope(study):
    client, headers, _, _ = study
    assert client.get("/api/v1/health").status_code == 200
    assert client.post("/api/v1/courses", json={"title": "x"}).status_code == 401
    course_id = course(study)
    bob = jwt.encode({"sub": "bob", "exp": 4102444800},
                     "test-secret-with-at-least-thirty-two-bytes", algorithm="HS256")
    response = client.get(f"/api/v1/courses/{course_id}/sources",
                          headers={"Authorization": "Bearer " + bob})
    assert response.status_code == 404
    assert client.get("/api/v1/courses", headers=headers).json()["courses"][0]["id"] == course_id


def test_auth_fails_closed_without_secret(study, monkeypatch):
    client, headers, _, _ = study
    monkeypatch.delenv("JWT_SECRET")
    assert client.get("/api/v1/courses", headers=headers).status_code == 503


def test_slide_to_draft_items_and_repeat_proposal(study):
    import json

    from test_concepts import concept
    from test_items import item_batch

    from app.llm import FakeLLM

    client, headers, app, _ = study
    course_id = course(study)
    upload(study, course_id)
    app.state.llm_client = FakeLLM({"": json.dumps({"concepts": [concept()]})})
    response = client.post(f"/api/v1/courses/{course_id}/concepts:propose", headers=headers)
    assert response.status_code == 200, response.text
    concept_id = response.json()["concepts"][0]["id"]
    assert client.post(f"/api/v1/courses/{course_id}/concepts:propose", headers=headers).json()["concepts"][0]["id"] == concept_id
    assert client.post(f"/api/v1/concepts/{concept_id}/items:generate", headers=headers).status_code == 409
    assert client.patch(f"/api/v1/concepts/{concept_id}", headers=headers,
                        json={"confirmed": True}).status_code == 200
    source_id = client.get(f"/api/v1/courses/{course_id}/sources", headers=headers).json()["sources"][0]["id"]
    app.state.llm_client = FakeLLM({"": json.dumps({"items": item_batch(source_id)})})
    generated = client.post(f"/api/v1/concepts/{concept_id}/items:generate", headers=headers)
    assert generated.status_code == 200, generated.text
    rows = generated.json()["items"]
    assert len(rows) == 3
    assert all(row["status"] == "draft" and row["source"]["page"] == 1 for row in rows)
    assert len(client.get(f"/api/v1/concepts/{concept_id}/items", headers=headers).json()["items"]) == 3
    bob = jwt.encode({"sub": "bob", "exp": 4102444800},
                     "test-secret-with-at-least-thirty-two-bytes", algorithm="HS256")
    for path in (f"/api/v1/courses/{course_id}/concepts", f"/api/v1/concepts/{concept_id}/items"):
        assert client.get(path, headers={"Authorization": "Bearer " + bob}).status_code == 404
    bob_headers = {"Authorization": "Bearer " + bob}
    assert client.post(f"/api/v1/courses/{course_id}/sources", headers=bob_headers,
                       files={"file": ("other.pdf", pdf_bytes(), "application/pdf")}).status_code == 404
    assert client.post(f"/api/v1/courses/{course_id}/concepts:propose", headers=bob_headers).status_code == 404
    assert client.patch(f"/api/v1/concepts/{concept_id}", headers=bob_headers,
                        json={"confirmed": False}).status_code == 404
    assert client.post(f"/api/v1/concepts/{concept_id}/items:generate", headers=bob_headers).status_code == 404
    assert upload(study, course_id).status_code == 409
    assert client.get(f"/api/v1/concepts/{concept_id}/items", headers=headers).json()["items"] == rows
    app.state.llm_client = FakeLLM({"": json.dumps({"items": [item_batch(source_id)[0], {"type": "short"}]})})
    assert client.post(f"/api/v1/concepts/{concept_id}/items:generate", headers=headers).status_code == 502
    assert len(client.get(f"/api/v1/concepts/{concept_id}/items", headers=headers).json()["items"]) == 3


@pytest.mark.parametrize("claims,secret", [
    ({"sub": "alice", "exp": 4102444800}, "wrong-signature-secret-at-least-thirty-two-bytes"),
    ({"sub": "alice", "exp": 1}, "test-secret-with-at-least-thirty-two-bytes"),
    ({"sub": "absent", "exp": 4102444800}, "test-secret-with-at-least-thirty-two-bytes"),
    ({"sub": "alice"}, "test-secret-with-at-least-thirty-two-bytes"),
])
def test_invalid_tokens_cannot_read_courses(study, claims, secret):
    client, _, _, _ = study
    token = jwt.encode(claims, secret, algorithm="HS256")
    assert client.get("/api/v1/courses", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_bad_model_response_does_not_partly_save(study):
    import json

    from test_concepts import concept

    from app.llm import FakeLLM

    client, headers, app, _ = study
    course_id = course(study)
    upload(study, course_id)
    app.state.llm_client = FakeLLM({"": json.dumps({"concepts": [concept(), {"slug": "broken"}]})})
    response = client.post(f"/api/v1/courses/{course_id}/concepts:propose", headers=headers)
    assert response.status_code == 502
    assert client.get(f"/api/v1/courses/{course_id}/concepts", headers=headers).json()["concepts"] == []


def test_question_generation_keeps_the_correct_file_when_page_numbers_repeat(study):
    import json

    from test_concepts import concept
    from test_items import item_batch

    from app.llm import FakeLLM

    client, headers, app, _ = study
    course_id = course(study)
    upload(study, course_id, name="a.pdf")
    upload(study, course_id, name="b.pdf")
    upload(study, course_id, name="c.pdf")
    upload(study, course_id, name="z.pdf")
    app.state.llm_client = FakeLLM({
        '"file_name": "a.pdf"': '{"concepts": []}',
        '"file_name": "b.pdf"': '{"concepts": []}',
        '"file_name": "c.pdf"': '{"concepts": []}',
        '"file_name": "z.pdf"': json.dumps({"concepts": [concept()]}),
    })
    response = client.post(f"/api/v1/courses/{course_id}/concepts:propose", headers=headers)
    concept_id = response.json()["concepts"][0]["id"]
    client.patch(f"/api/v1/concepts/{concept_id}", headers=headers, json={"confirmed": True})
    rows = client.get(f"/api/v1/courses/{course_id}/sources", headers=headers).json()["sources"]
    source_id = next(row["id"] for row in rows if row["file_name"] == "z.pdf" and row["page"] == 1)
    app.state.llm_client = FakeLLM({"": json.dumps({"items": item_batch(source_id)})})
    result = client.post(f"/api/v1/concepts/{concept_id}/items:generate", headers=headers)
    assert len(result.json()["items"]) == 3
    assert all(row["source"]["file_name"] == "z.pdf" for row in result.json()["items"])
