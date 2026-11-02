"""PDF ingest (#13): one source row per page, strict input checks, owner-only."""

import pytest
from conftest import make_pdf, register

from app.ingest import MAX_UPLOAD_BYTES
from assistant.backend.models import Source


@pytest.fixture
def course(client, headers):
    response = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014", "level": "university"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, course, content, name="week01.pdf"):
    return client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers,
        files={"file": (name, content, "application/pdf")},
    )


def rows(app, course):
    with app.state.database.sessions() as db:
        return (
            db.query(Source)
            .filter_by(course_id=course["id"])
            .order_by(Source.file_name, Source.page)
            .all()
        )


def test_health_is_public(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_three_page_pdf_stores_three_numbered_pages(client, app, headers, course, sample_pdf):
    response = upload(client, headers, course, sample_pdf)
    assert response.status_code == 201, response.text
    assert response.json() == {
        "file_name": "week01.pdf",
        "pages": 3,
        "status": "processed",
        "warning": None,
    }
    stored = rows(app, course)
    assert [(row.page, row.text) for row in stored] == [
        (1, "alpha lecture"),  # whitespace normalized
        (2, "beta lecture"),
        (3, "gamma lecture"),
    ]
    listed = client.get(f"/api/v1/courses/{course['id']}/sources", headers=headers)
    assert [row["page"] for row in listed.json()] == [1, 2, 3]


def test_reupload_replaces_pages_of_the_same_file(client, app, headers, course, sample_pdf):
    assert upload(client, headers, course, sample_pdf).status_code == 201
    assert upload(client, headers, course, make_pdf("only")).status_code == 201
    assert upload(client, headers, course, sample_pdf, "week02.pdf").status_code == 201
    assert upload(client, headers, course, sample_pdf).status_code == 201
    assert len(rows(app, course)) == 6
    assert sum(row.file_name == "week01.pdf" for row in rows(app, course)) == 3


@pytest.mark.parametrize(
    ("name", "content", "status", "detail"),
    [
        ("notes.pdf", b"plain text renamed to pdf", 415, "not_pdf"),
        ("slides.txt", make_pdf("alpha"), 415, "not_pdf"),
        ("empty.pdf", b"", 400, "invalid_pdf"),
        ("broken.pdf", b"%PDF-1.7\nthis is not a real document", 400, "invalid_pdf"),
    ],
)
def test_rejects_bad_files_without_storing(
    client, app, headers, course, name, content, status, detail
):
    response = upload(client, headers, course, content, name)
    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert rows(app, course) == []


def test_rejects_files_over_20_mb(client, app, headers, course):
    content = b"%PDF-1.7\n" + b"0" * MAX_UPLOAD_BYTES
    response = upload(client, headers, course, content)
    assert (response.status_code, response.json()["detail"]) == (413, "file_too_large")
    assert rows(app, course) == []


def test_mostly_empty_pdf_is_stored_with_scanned_warning(client, app, headers, course):
    # Exactly 80% empty is not "more than 80%".
    border = upload(client, headers, course, make_pdf("", "", "", "", "title"))
    assert border.json()["warning"] is None
    response = upload(client, headers, course, make_pdf("", "", "", "", "", "title"))
    assert response.status_code == 201
    assert response.json()["pages"] == 6
    assert response.json()["warning"] == "scanned_pdf"
    assert len(rows(app, course)) == 6  # empty pages kept so numbers match the file


def test_windows_path_in_file_name_keeps_only_base_name(client, app, headers, course, sample_pdf):
    response = upload(client, headers, course, sample_pdf, r"C:\Users\me\week01.pdf")
    assert response.json()["file_name"] == "week01.pdf"


def test_courses_are_private_to_their_owner(client, headers, course, sample_pdf):
    other = register(client, "Thang", "thang@example.com")
    other_headers = {"Authorization": "Bearer " + other["access_token"]}
    assert upload(client, other_headers, course, sample_pdf).status_code == 404
    assert (
        client.get(f"/api/v1/courses/{course['id']}/sources", headers=other_headers).status_code
        == 404
    )
    assert client.get("/api/v1/courses", headers=other_headers).json() == []
    assert upload(client, {}, course, sample_pdf).status_code == 401
    assert client.post("/api/v1/courses", json={"title": "x"}).status_code == 401
