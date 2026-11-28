"""Search providers, PII filtering, fallback, and ``search_runs`` tests (#61)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.db import get_engine, get_session, init_db
from app.search.base import Candidate, SearchProvider
from app.search.catalog import CatalogSearch
from app.search.fake import FakeSearch
from app.search.pii_filter import contains_pii, filter_pii
from app.search.service import SearchService, generate_queries
from app.search.web import WebSearch
from app.search.youtube import YouTubeSearch

VIETNAMESE = re.compile(
    r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
    re.IGNORECASE,
)
ENGLISH = re.compile(
    r"\b(?:lecture|notes|tutorial|video|worked|examples|filetype)\b",
    re.IGNORECASE,
)
FORMAT = re.compile(r"filetype|pdf|video", re.IGNORECASE)


def _catalog_yaml() -> str:
    return """\
resources:
  - title: "Problem framing and the solution ladder"
    url: "https://example.test/problem-framing"
    kind: article
    lang: en
    snippet: "Lecture notes for CSC10014."
    tags: [problem framing, solution ladder, CSC10014, lecture notes]
  - title: "Problem framing video"
    url: "https://example.test/problem-framing-video"
    kind: video
    lang: en
    snippet: "A short lecture video."
    tags: [problem framing, CSC10014, lecture video]
"""


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "catalog"
    directory.mkdir()
    (directory / "resources.yaml").write_text(_catalog_yaml(), encoding="utf-8")
    return directory


class RecordingSearch(SearchProvider):
    """Capture exactly what the service would send to an external provider."""

    name = "recording"

    def __init__(
        self,
        *,
        results: list[Candidate] | None = None,
        error: Exception | None = None,
        name: str = "recording",
    ):
        self.name = name
        self.results = results or []
        self.error = error
        self.queries: list[str] = []

    def search(
        self,
        query: str,
        *,
        lang: str = "vi",
        kind: str | None = None,
        safe: bool = True,
    ) -> list[Candidate]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return list(self.results)


def test_catalog_reads_yaml_and_matches_both_languages(catalog_dir: Path):
    catalog = CatalogSearch(catalog_dir)
    results = catalog.search("Problem framing CSC10014 lecture notes filetype:pdf")
    assert results[0].title == "Problem framing and the solution ladder"
    assert {candidate.provider for candidate in results} == {"catalog"}

    videos = catalog.search("Problem framing", kind="video")
    assert [candidate.kind for candidate in videos] == ["video"]

    vietnamese = catalog.search("Problem framing bài giảng")
    assert vietnamese, "accent-insensitive Vietnamese matching should still work"


def test_generate_queries_has_vietnamese_english_and_format():
    queries = generate_queries("Problem framing", "CSC10014")
    assert 3 <= len(queries) <= 5
    assert any(VIETNAMESE.search(query) for query in queries)
    assert any(ENGLISH.search(query) for query in queries)
    assert any(FORMAT.search(query) for query in queries)


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("Liên hệ a.student+test@hcmut.edu.vn để biết thêm", "a.student+test@hcmut.edu.vn"),
        ("Hotline: 090 123 4567", "090 123 4567"),
        ("Hotline: +84 90 123 4567", "+84 90 123 4567"),
        ("MSSV: 20521234", "20521234"),
        ("Student ID: 2112345", "2112345"),
        ("Giảng viên: ThS. Nguyễn Văn An", "Nguyễn Văn An"),
        ("GVHD: PGS.TS. Trần Thị Bích Ngọc", "Trần Thị Bích Ngọc"),
        ("Sinh viên thực hiện: Lê Hoàng Dũng", "Lê Hoàng Dũng"),
        ("Họ và tên: Phạm Minh Châu", "Phạm Minh Châu"),
        ("Tên SV: Nguyễn Văn An", "Nguyễn Văn An"),
        ("Tên GV: Nguyễn Văn An", "Nguyễn Văn An"),
        ("Họ tên sinh viên: Trần Thị Bích Ngọc", "Trần Thị Bích Ngọc"),
        ("Thầy Đỗ Quang Huy hướng dẫn", "Đỗ Quang Huy"),
        ("Nguyễn Văn An là giảng viên phụ trách", "Nguyễn Văn An"),
        ("| Giảng viên | Nguyễn Văn An |", "Nguyễn Văn An"),
        ("Do Van An is the instructor", "Do Van An"),
        ("NGUYEN VAN AN teaches the course", "NGUYEN VAN AN"),
    ],
)
def test_filter_pii_masks_each_kind(raw: str, secret: str):
    filtered = filter_pii(raw)
    assert secret not in filtered
    assert contains_pii(raw)
    assert not contains_pii(filtered)


def test_youtube_500_and_quota_return_empty_lists():
    for status in (500, 429):
        transport = httpx.MockTransport(
            lambda request, code=status: httpx.Response(code)
        )
        with httpx.Client(transport=transport) as client:
            provider = YouTubeSearch(api_key="test-key", client=client)
            assert provider.search("problem framing") == []
            assert provider.last_error == f"http_{status}"


def test_web_500_and_quota_return_empty_lists():
    for status in (500, 429):
        transport = httpx.MockTransport(
            lambda request, code=status: httpx.Response(code)
        )
        with httpx.Client(transport=transport) as client:
            provider = WebSearch(api_key="test-key", client=client)
            assert provider.search("problem framing") == []
            assert provider.last_error == f"http_{status}"


def test_youtube_parses_a_video_search_response():
    payload = {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "Problem framing lecture",
                    "description": "A lecture about <b>framing</b> problems.",
                },
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        results = YouTubeSearch(api_key="test-key", client=client).search(
            "problem framing", lang="en"
        )
    assert results == [
        Candidate(
            url="https://www.youtube.com/watch?v=abc123",
            title="Problem framing lecture",
            provider="youtube",
            kind="video",
            lang="en",
            snippet="A lecture about framing problems.",
        )
    ]


def test_web_parses_serper_response():
    payload = {
        "organic": [
            {
                "link": "https://example.test/notes",
                "title": "Problem framing notes",
                "snippet": "Worked examples.",
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        results = WebSearch(api_key="test-key", client=client).search(
            "problem framing", lang="en"
        )
    assert results[0].url == "https://example.test/notes"
    assert results[0].provider == "web"
    assert results[0].kind == "article"


def test_external_failure_still_returns_catalog_results(catalog_dir: Path):
    catalog = CatalogSearch(catalog_dir)
    youtube = RecordingSearch(error=RuntimeError("HTTP 500"), name="youtube")
    web = RecordingSearch(error=RuntimeError("quota exceeded"), name="web")
    service = SearchService([youtube, catalog, web], max_results=10)

    results = service.search("Problem framing", "CSC10014")

    assert results
    assert {candidate.provider for candidate in results} == {"catalog"}
    assert service.last_errors == {
        "youtube": "RuntimeError",
        "web": "RuntimeError",
    }
    assert service.last_runs
    assert any(run.status == "error" for run in service.last_runs)


def test_media_query_uses_only_pii_filtered_queries():
    syllabus = (
        "Giảng viên: ThS. Nguyễn Văn An (an.nguyen@hcmut.edu.vn, 090 123 4567)\n"
        "Sinh viên: Lê Hoàng Dũng - MSSV: 20521234 - dung.le@hcmut.edu.vn"
    )
    recorder = RecordingSearch(name="youtube")
    service = SearchService([recorder], max_results=100)

    service.search(syllabus, "CSC10014")

    assert recorder.queries
    for query in recorder.queries:
        assert "Nguyễn Văn An" not in query
        assert "Lê Hoàng Dũng" not in query
        assert "an.nguyen@hcmut.edu.vn" not in query
        assert "dung.le@hcmut.edu.vn" not in query
        assert "20521234" not in query
        assert "090 123 4567" not in query
        assert filter_pii(query) == query


def test_ten_pii_syllabi_produce_zero_pii_queries():
    syllabi = [
        (
            f"Giảng viên: ThS. Nguyễn Văn An\n"
            f"Email: an.nguyen{i}@hcmut.edu.vn\n"
            f"MSSV: 2052123{i}\n"
            f"Hotline: 090 123 45{60 + i:02d}"
        )
        for i in range(10)
    ]
    names = ["Nguyễn Văn An"]
    emails = [f"an.nguyen{i}@hcmut.edu.vn" for i in range(10)]
    ids = [f"2052123{i}" for i in range(10)]
    phones = [f"090 123 45{60 + i:02d}" for i in range(10)]

    recorder = RecordingSearch(name="external")
    service = SearchService([recorder], max_results=100)
    for syllabus in syllabi:
        service.search(syllabus, "CSC10014")

    external_queries = recorder.queries
    assert len(external_queries) == 50
    for query in external_queries:
        for secret in (*names, *emails, *ids, *phones):
            assert secret not in query
        assert filter_pii(query) == query


def test_search_runs_records_only_filtered_query(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'search.db').as_posix()}"
    init_db(database_url=url, reset=True)
    session = get_session(url)
    try:
        session.execute(
            text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, :email, :password_hash)"
            ),
            {"id": "u_1", "email": "u1@example.com", "password_hash": "x"},
        )
        catalog = CatalogSearch(tmp_path / "catalog")
        catalog.directory.mkdir()
        (catalog.directory / "resources.yaml").write_text(
            _catalog_yaml(), encoding="utf-8"
        )
        external = RecordingSearch(error=RuntimeError("quota"), name="youtube")
        service = SearchService([catalog, external], max_results=10)

        service.search(
            "Problem framing - GV: Nguyễn Văn An - MSSV: 20521234",
            "CSC10014",
            session=session,
            user_id="u_1",
        )
        session.commit()

        rows = session.execute(
            text("SELECT query, provider, status, results_count FROM search_runs")
        ).all()
        assert rows
        assert any(row[1] == "catalog" and row[2] == "ok" for row in rows)
        assert any(row[1] == "youtube" and row[2] == "error" for row in rows)
        for row in rows:
            assert "Nguyễn Văn An" not in row[0]
            assert "20521234" not in row[0]
            assert filter_pii(row[0]) == row[0]
    finally:
        session.close()
        get_engine(url).dispose()


def test_fake_search_is_offline_and_deterministic():
    provider = FakeSearch()
    first = provider.search("anything", lang="vi")
    second = provider.search("anything", lang="vi")
    assert first == second
    assert first
    assert provider.calls == 2
