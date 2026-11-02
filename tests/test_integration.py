"""Integration tests for Ingest, Retrieval, and Auth (Issue #16).

Tests independent end-to-end integration across modules:
1. Ingest: valid 3-page PDF, corrupted PDF, unsupported media type, payload too large.
2. Retrieval: BM25 keyword matching, ranking, unknown keyword, empty course handling.
3. Auth: wrong password, expired token, cross-user isolation (IDOR), missing header.
4. End-to-End: full flow from registration to course creation, ingest, and retrieval.
"""

from __future__ import annotations

from datetime import timedelta

from app.retrieval import BM25Retriever
from assistant.backend.models import Source


# Helper function to create a test course
def create_course(client, headers, title="CSC10014", level="university"):
    response = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": title, "level": level},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ============================================================================
# 1. INGEST INTEGRATION TESTS (4 tests)
# ============================================================================

def test_ingest_three_page_pdf_success(client, app, headers_a, sample_pdf):
    """Uploading a 3-page PDF extracts exactly 3 source rows in the database."""
    course = create_course(client, headers_a, "Physics 101")
    response = client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers_a,
        files={"file": ("physics.pdf", sample_pdf, "application/pdf")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["file_name"] == "physics.pdf"
    assert payload["pages"] == 3
    assert payload["status"] == "processed"

    # Verify rows stored in database
    with app.state.database.sessions() as db:
        stored = (
            db.query(Source)
            .filter_by(course_id=course["id"])
            .order_by(Source.page)
            .all()
        )
        assert len(stored) == 3
        assert [s.page for s in stored] == [1, 2, 3]


def test_ingest_corrupted_pdf_rejected_400(client, headers_a):
    """Uploading corrupted PDF bytes returns HTTP 400 Bad Request."""
    course = create_course(client, headers_a, "Math 101")
    corrupted_bytes = b"%PDF-1.4 corrupted invalid bytes here"
    response = client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers_a,
        files={"file": ("corrupt.pdf", corrupted_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert "detail" in response.json()


def test_ingest_unsupported_file_type_rejected_415(client, headers_a):
    """Uploading non-PDF file (.txt) returns HTTP 415 Unsupported Media Type."""
    course = create_course(client, headers_a, "Literature")
    response = client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers_a,
        files={"file": ("notes.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 415


def test_ingest_oversized_file_rejected_413(client, headers_a):
    """Uploads with Content-Length exceeding limit are rejected with HTTP 413."""
    course = create_course(client, headers_a, "Large Course")
    response = client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers={**headers_a, "content-length": "23000000"},
        files={"file": ("huge.pdf", b"%PDF-1.4 mock", "application/pdf")},
    )
    assert response.status_code == 413


# ============================================================================
# 2. RETRIEVAL INTEGRATION TESTS (3 tests)
# ============================================================================

def test_retrieval_keyword_beta_ranks_page_2_first(client, headers_a, sample_pdf):
    """BM25 query for 'beta' places Page 2 at top rank."""
    course = create_course(client, headers_a, "Algorithm")
    client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers_a,
        files={"file": ("algo.pdf", sample_pdf, "application/pdf")},
    )

    sources_res = client.get(f"/api/v1/courses/{course['id']}/sources", headers=headers_a)
    assert sources_res.status_code == 200
    sources = sources_res.json()
    assert len(sources) == 3

    # Short 3-page slides produce raw BM25 ~0.51, so we test ranking with min_score=0.1
    retriever = BM25Retriever(sources)
    hits = retriever.retrieve("beta", top_k=3, min_score=0.1)
    assert len(hits) >= 1
    assert hits[0].page == 2


def test_retrieval_unknown_keyword_returns_empty(client, headers_a, sample_pdf):
    """Querying an unknown term ('zzzz') returns empty list below threshold."""
    course = create_course(client, headers_a, "Data Structures")
    client.post(
        f"/api/v1/courses/{course['id']}/sources",
        headers=headers_a,
        files={"file": ("ds.pdf", sample_pdf, "application/pdf")},
    )

    sources_res = client.get(f"/api/v1/courses/{course['id']}/sources", headers=headers_a)
    sources = sources_res.json()

    retriever = BM25Retriever(sources)
    hits = retriever.retrieve("zzzz", top_k=3, min_score=0.1)
    assert hits == []


def test_retrieval_empty_course_sources_returns_empty(client, headers_a):
    """Retrieval on a course with zero sources safely returns an empty list."""
    course = create_course(client, headers_a, "Empty Course")
    sources_res = client.get(f"/api/v1/courses/{course['id']}/sources", headers=headers_a)
    sources = sources_res.json()
    assert sources == []

    retriever = BM25Retriever(sources)
    hits = retriever.retrieve("any keyword", top_k=3, min_score=0.1)
    assert hits == []


# ============================================================================
# 3. AUTH & SECURITY INTEGRATION TESTS (4 tests)
# ============================================================================

def test_auth_login_wrong_password_rejected_401(client):
    """Login with invalid password returns HTTP 401."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "lan@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_auth_expired_token_rejected_401(client, clock):
    """Request with an expired token is rejected with HTTP 401."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "name": "ShortSession",
            "email": "short@example.com",
            "password": "correct-horse-123",
            "birth_year": 2000,
        },
    ).json()
    token = reg["access_token"]

    # Advance clock past session expiry
    clock[0] = clock[0] + timedelta(days=60)

    response = client.get("/api/v1/courses", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401


def test_auth_cross_user_course_access_denied_404(client, headers_a, headers_b):
    """User B cannot access or list sources from Course owned by User A (IDOR prevention)."""
    course_a = create_course(client, headers_a, "Private Course A")

    response = client.get(
        f"/api/v1/courses/{course_a['id']}/sources",
        headers=headers_b,
    )
    assert response.status_code == 404


def test_auth_missing_header_rejected_401(client):
    """Protected endpoints reject requests missing the Authorization header."""
    response = client.get("/api/v1/courses")
    assert response.status_code == 401


# ============================================================================
# 4. END-TO-END FLOW TEST (1 test)
# ============================================================================

def test_e2e_register_create_course_upload_and_retrieve(client, sample_pdf):
    """Full end-to-end integration: Register -> Course -> Upload PDF -> BM25 Retrieve."""
    # 1. Register new user
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "name": "E2E User",
            "email": "e2e@example.com",
            "password": "correct-horse-123",
            "birth_year": 2002,
        },
    )
    assert reg_res.status_code == 201
    auth_header = {"Authorization": "Bearer " + reg_res.json()["access_token"]}

    # 2. Create course
    course_res = client.post(
        "/api/v1/courses",
        headers=auth_header,
        json={"title": "Software Engineering", "level": "university"},
    )
    assert course_res.status_code == 201
    course_id = course_res.json()["id"]

    # 3. Upload 3-page PDF
    upload_res = client.post(
        f"/api/v1/courses/{course_id}/sources",
        headers=auth_header,
        files={"file": ("syllabus.pdf", sample_pdf, "application/pdf")},
    )
    assert upload_res.status_code == 201
    assert upload_res.json()["pages"] == 3

    # 4. Retrieve sources from API
    sources_res = client.get(f"/api/v1/courses/{course_id}/sources", headers=auth_header)
    assert sources_res.status_code == 200
    sources = sources_res.json()
    assert len(sources) == 3

    # 5. Perform BM25 retrieval for keyword 'alpha' (present on Page 1)
    retriever = BM25Retriever(sources)
    hits = retriever.retrieve("alpha", top_k=1, min_score=0.1)
    assert len(hits) == 1
    assert hits[0].page == 1
