"""Ingest (#13, #49): one source row per page of a PDF, DOCX or text file, strict input
checks, owner-only."""

import zipfile
from io import BytesIO

import docx
import pytest
from conftest import make_pdf, register

from app.ingest import MAX_UPLOAD_BYTES, PAGE_CHARS
from assistant.backend.models import Source


@pytest.fixture
def course(client, headers):
    response = client.post(
        "/api/v1/courses", headers=headers, json={"title": "CSC10014", "level": "university"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, course, content, name="week01.pdf", **form):
    # The client's content type is ignored: the server checks the name and leading bytes.
    return client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers,
        files={"file": (name, content, "application/pdf")},
        data=form,
    )


def make_docx(*pages):
    """A real DOCX with a hard page break between the given page texts."""
    document = docx.Document()
    for number, text in enumerate(pages):
        if number:
            document.add_page_break()
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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
        "kind": "material",
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
        ("notes.pdf", b"plain text renamed to pdf", 415, "unsupported_type"),
        ("slides.txt", make_pdf("alpha"), 415, "unsupported_type"),
        ("slides.pptx", b"PK\x03\x04", 415, "unsupported_type"),
        ("broken.docx", b"PK\x03\x04 truncated", 400, "invalid_file"),
        ("blank.txt", b" \n\n ", 400, "invalid_file"),
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


def test_two_page_docx_syllabus_stores_two_pages_without_vision(client, app, headers, course):
    content = make_docx("Tuần 1: Problem framing", "Giữa kỳ 30%")
    response = upload(client, headers, course, content, "syllabus.docx", kind="syllabus")
    assert response.status_code == 201, response.text
    assert (response.json()["pages"], response.json()["kind"]) == (2, "syllabus")
    assert response.json()["warning"] is None
    stored = rows(app, course)
    assert [(row.page, row.text, row.kind) for row in stored] == [
        (1, "Tuần 1: Problem framing", "syllabus"),
        (2, "Giữa kỳ 30%", "syllabus"),
    ]
    assert all(row.visual_notes is None for row in stored)  # only PDFs go to the vision model
    listed = client.get(f"/api/v1/courses/{course['id']}/sources", headers=headers).json()
    assert {row["kind"] for row in listed} == {"syllabus"}


def test_pasted_text_is_cut_into_pages_of_at_most_3000_characters(
    client, app, headers, course
):
    words = ("Tuần 1 ôn tập chuẩn đầu ra CLO1. " * 200).encode("utf-8")  # about 6,600 chars
    response = upload(client, headers, course, words, "course-page.txt")
    assert response.status_code == 201, response.text
    stored = rows(app, course)
    assert response.json()["pages"] == len(stored) == 3
    assert all(0 < len(row.text) <= PAGE_CHARS for row in stored)
    assert {row.kind for row in stored} == {"material"}  # the default


def test_zip_that_is_not_a_word_document_is_unsupported(client, app, headers, course):
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("notes.txt", "not a Word document")
    response = upload(client, headers, course, archive.getvalue(), "fake.docx")
    assert (response.status_code, response.json()["detail"]) == (415, "unsupported_type")
    assert rows(app, course) == []


def test_rejects_docx_over_20_mb(client, app, headers, course):
    content = make_docx("x") + b"0" * (21 * 1024 * 1024)
    response = upload(client, headers, course, content, "big.docx")
    assert (response.status_code, response.json()["detail"]) == (413, "file_too_large")
    assert rows(app, course) == []


def test_unknown_source_kind_is_rejected(client, app, headers, course, sample_pdf):
    response = upload(client, headers, course, sample_pdf, kind="homework")
    assert response.status_code == 422
    assert rows(app, course) == []

def test_pdf_syllabus_preserves_lines_for_offline_preview(client, headers, course):
    """#56: upload normalization must not collapse the lines the #59 parser reads."""
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "eval/syllabus/01_csc10014_problem_framing.pdf"
    response = upload(client, headers, course, fixture.read_bytes(), "CSC10014.pdf", kind="syllabus")
    assert response.status_code == 201
    parsed = client.post(
        f"/api/v1/courses/{course['id']}/syllabus:parse",
        headers=headers,
        json={"file_name": "CSC10014.pdf"},
    )
    assert parsed.status_code == 200, parsed.text
    draft = parsed.json()
    assert len(draft["parsed"]["outcomes"]) == 4
    assert len(draft["parsed"]["weeks"]) == 10
    assert len(draft["parsed"]["assessments"]) == 3
    assert draft["can_confirm"] is True

def test_pasted_syllabus_preview_returns_exact_page_evidence(client, headers, course):
    text = "CLO1: Frame a problem.\n" + "Notes about the course.\n" * 150 + "Week 1: Framing\nFinal: 100% (week 1)"
    response = client.post(
        f"/api/v1/courses/{course['id']}/syllabus:parse", headers=headers, json={"text": text}
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["pages"] > 1
    assert len(draft["source_pages"]) == draft["pages"]
    for row in draft["parsed"]["weeks"]:
        assert row["topics"][0] in draft["source_pages"][str(row["source_page"])]
