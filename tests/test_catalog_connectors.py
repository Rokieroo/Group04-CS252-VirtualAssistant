"""Issue #98: catalog connectors, idempotent upsert and syllabus-driven demand.

Offline: connectors read trimmed copies of real provider responses in
tests/fixtures/catalog (MIT OCW sitemaps and course page, the OpenStax CMS API,
taken 2026-11-05) through a fake fetcher; nothing touches the network.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.catalog.connectors import (
    CONNECTORS,
    MANUAL_FILES,
    OPEN_YALE_FILE,
    CatalogRecord,
    ConnectorError,
    FakeConnector,
    ManualYamlConnector,
    UnitRecord,
    build_connectors,
    check_record,
    wanted,
)
from app.catalog.connectors.base import relevant
from app.catalog.connectors.openstax import book
from app.catalog.demand import SyllabusDemand, node_subjects, priority_batches
from app.catalog.sources import load_sources
from app.vetting.fetch import FetchResult
from assistant.backend.catalog_ingest import ingest, node_candidates, upsert_records
from assistant.backend.catalog_models import (
    CatalogEmbedding,
    CatalogUnit,
    ResourceSubject,
)
from assistant.backend.models import CatalogCourse, Resource

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/catalog"
CSC10014 = ROOT / "eval/syllabus/01_csc10014_problem_framing.gold.json"
NOW = datetime(2026, 11, 5, tzinfo=UTC)
COURSE = "https://ocw.mit.edu/courses/6-0002-introduction-to-computational-thinking-and-data-science-fall-2016/"
AI_COURSE = "https://ocw.mit.edu/courses/6-034-artificial-intelligence-fall-2010/"


class FakeFetcher:
    """Serves fixture files by exact URL, or by prefix for keys ending in "?"."""

    def __init__(self, routes):
        self.routes = routes
        self.seen = []

    def fetch(self, url):
        self.seen.append(url)
        for key, name in self.routes.items():
            if url == key or (key.endswith("?") and url.startswith(key)):
                return FetchResult(url=url, status=200, body=(FIXTURES / name).read_bytes())
        return FetchResult(url=url, status=404)


def mit():
    return FakeFetcher({
        "https://ocw.mit.edu/sitemap.xml": "mit_ocw_sitemap.xml",
        COURSE: "mit_ocw_course.html",
        COURSE + "sitemap.xml": "mit_ocw_course_sitemap.xml",
    })


def connector(name, fetcher):
    return build_connectors(fetcher, [name])[0]


def record(title="Use case diagram", url="https://en.wikipedia.org/wiki/Use_case_diagram", **changes):
    values = {
        "provider": "manual",
        "external_id": url,
        "title": title,
        "url": url,
        "license": "CC-BY-SA-4.0",
        "subjects": ("ct.use-cases",),
    }
    return CatalogRecord(**{**values, **changes})


def demand(path=CSC10014):
    return SyllabusDemand.from_gold(json.loads(path.read_text(encoding="utf-8")))


def counts(db):
    return {
        model.__name__: db.scalar(select(func.count()).select_from(model))
        for model in (CatalogCourse, Resource, CatalogUnit, ResourceSubject, CatalogEmbedding)
    }


# --- connectors -------------------------------------------------------------------


def test_wanted_adds_topics_and_parents_but_not_the_root_field():
    found = wanted(["ct.framing", "ds"])
    assert {"ct.framing", "ct", "ds", "ds.trees"} <= found
    assert "computing" not in found and "ct.ladder" not in found


def test_mit_ocw_reads_only_courses_whose_slug_matches_the_subjects():
    fetcher = mit()
    records = list(connector("mit_ocw", fetcher).fetch(["ct.framing", "ai"]))

    assert [r.external_id for r in records] == [
        "6-0002-introduction-to-computational-thinking-and-data-science-fall-2016",
        "6-034-artificial-intelligence-fall-2010",
    ]
    course = records[0]
    # From the course page: its own title, department, number and level.
    assert course.title == "Introduction to Computational Thinking and Data Science"
    assert course.department == "Electrical Engineering and Computer Science"
    assert (course.code, course.year, course.level) == ("6.0002", 2016, "undergrad")
    assert (course.provider, course.license) == ("mit_ocw", "CC-BY-NC-SA-4.0")
    # Section pages are units, sorted by URL; syllabus, insights and files are not.
    assert [(u.position, u.title, u.format) for u in course.units] == [
        (1, "Assignments", "article"),
        (2, "Lecture slides and files", "article"),
        (3, "Readings", "article"),
        (4, "Software", "article"),
        (5, "Lecture videos", "video"),
    ]
    # A course page that fails leaves the slug's title; unmatched courses cost nothing.
    assert records[1].title == "Artificial intelligence" and records[1].units == ()
    assert fetcher.seen == [
        "https://ocw.mit.edu/sitemap.xml",
        COURSE,
        COURSE + "sitemap.xml",
        AI_COURSE,
        AI_COURSE + "sitemap.xml",
    ]


def test_mit_ocw_reports_an_unreadable_index():
    with pytest.raises(ConnectorError, match="index_404"):
        list(connector("mit_ocw", FakeFetcher({})).fetch(["ai"]))


def test_openstax_reads_the_license_of_each_book():
    provider = load_sources().providers["openstax"]
    items = json.loads((FIXTURES / "openstax_books.json").read_text(encoding="utf-8"))["items"]
    books = {item["meta"]["slug"]: book(provider, item, "api") for item in items}

    assert books["college-physics-courseware"] is None  # retired
    assert books["statistics"].license == "CC-BY-4.0"
    assert books["statistics"].url == "https://openstax.org/details/books/statistics"
    assert books["introduction-computer-science"].license == "CC-BY-NC-SA-4.0"
    unlicensed = next(b for slug, b in books.items() if slug.endswith("volumen-1"))
    # No license named: it waits for review instead of getting a default.
    assert (unlicensed.license, unlicensed.language) == (None, "es")
    assert check_record(unlicensed, load_sources()) is None
    # A blurb naming a topic in passing does not select the book; its title would.
    blurb = replace(books["statistics"], description="Covers CPU scheduling and threads.")
    assert not relevant(blurb, wanted(["os.process"]))
    assert relevant(replace(blurb, title="Operating Systems: Processes"), wanted(["os.process"]))


def test_openstax_pages_through_the_api(monkeypatch):
    from app.catalog.connectors import openstax

    monkeypatch.setattr(openstax, "PAGE_SIZE", 2)
    fetcher = FakeFetcher({"https://openstax.org/apps/cms/api/v2/pages/?": "openstax_books.json"})
    records = list(connector("openstax", fetcher).fetch(["computing"]))

    # The fake serves the same 5 books for every page: 3 pages cover total_count 5.
    assert [r.title for r in records] == ["Introduction to Computer Science"] * 3
    assert [u.rsplit("offset=", 1)[1] for u in fetcher.seen] == ["0", "2", "4"]
    assert all("limit=2" in u and "license_name" in u for u in fetcher.seen)


def test_hand_lists_read_entries_and_skip_broken_ones(tmp_path):
    path = tmp_path / "yale.yaml"
    path.write_text(
        "resources:\n"
        "  - {title: Game Theory, url: 'https://oyc.yale.edu/economics/econ-159',"
        " code: ECON 159, license: CC-BY-NC-SA-3.0, kind: course, tags: [game theory]}\n"
        "  - {title: No link}\n",
        encoding="utf-8",
    )
    [entry] = ManualYamlConnector([path], load_sources(), name="open_yale").records()
    # The registry provider owning the domain, not a field of the entry.
    assert (entry.provider, entry.code, entry.format) == ("open_yale", "ECON 159", "course")
    assert entry.keywords == ("game theory",)
    assert check_record(entry, load_sources()) is None


@pytest.mark.parametrize("path", [*MANUAL_FILES, OPEN_YALE_FILE], ids=lambda p: p.name)
def test_committed_hand_lists_are_lawful(path):
    sources = load_sources()
    records = list(ManualYamlConnector([path], sources).records())
    assert records
    assert [(r.url, check_record(r, sources)) for r in records if check_record(r, sources)] == []


def test_check_record_refuses_what_adr_004_forbids():
    sources = load_sources()
    assert check_record(record(license="CC-BY-ND-4.0"), sources) == "unknown_license"
    assert check_record(record(url="https://www.chegg.com/x"), sources) == "blocked_domain"
    assert check_record(record(subjects=("no.such",)), sources) == "unknown_subject"
    assert check_record(record(provider="coursera_clone"), sources) == "unknown_provider"
    course = record(provider="mit_ocw", url="https://ocw.mit.edu/courses/x/", license="CC-BY-NC-SA-4.0")
    assert check_record(course, sources) is None
    stray = replace(course, units=(UnitRecord(1, "Notes", "https://evil.example/notes"),))
    assert check_record(stray, sources) == "foreign_domain"
    assert check_record(replace(course, license=None), sources) == "missing_license"
    assert check_record(replace(course, provider="openalex"), sources) == "not_a_source_provider"


def test_no_connector_runs_for_a_provider_without_automated_access():
    sources = load_sources()
    locked = replace(sources.providers["mit_ocw"], automated=False)
    blocked = replace(sources, providers={**sources.providers, "mit_ocw": locked})
    with pytest.raises(ConnectorError, match="not_automatable_mit_ocw"):
        build_connectors(FakeFetcher({}), ["mit_ocw"], blocked)
    with pytest.raises(ConnectorError, match="unknown_connector_coursera"):
        build_connectors(FakeFetcher({}), ["coursera"])
    assert set(CONNECTORS) == {"mit_ocw", "openstax", "open_yale", "manual_yaml"}


def test_fake_connector_filters_by_subject_and_since():
    old = replace(record(), updated_at=datetime(2025, 1, 1, tzinfo=UTC))
    other = record("Binary trees", "https://en.wikipedia.org/wiki/Binary_tree", subjects=("ds.trees",))
    fake = FakeConnector([old, other])
    assert list(fake.fetch(["ct.use-cases"])) == [old]
    assert list(fake.fetch(["ct.use-cases"], since=NOW)) == []


# --- demand -----------------------------------------------------------------------


def test_priority_batches_ask_for_the_first_syllabus_first_without_repeats():
    first, second = demand(), demand(ROOT / "eval/syllabus/03_cs201_data_structures.gold.json")
    (_, csc), (_, ds) = priority_batches([first, second])
    assert {"ct.framing", "ct.requirements", "ct.use-cases", "ct.pipelines", "ct.project"} <= set(csc)
    assert ds and not set(ds) & set(csc)
    assert priority_batches([first, first])[1][1] == []


# --- upsert -----------------------------------------------------------------------


def test_second_run_creates_no_new_rows(app, client):
    records = list(connector("mit_ocw", mit()).fetch(["ct.framing", "ai"]))
    records += [record(), record("Use case", "https://en.wikipedia.org/wiki/Use_case")]
    with app.state.database.sessions() as db:
        first = upsert_records(db, records, connector="mit_ocw", now=NOW)
        db.commit()
        before, ids = counts(db), sorted(db.scalars(select(Resource.id)))
        second = upsert_records(db, records, connector="mit_ocw", now=NOW)
        db.commit()

        assert first.created == {"courses": 4, "resources": 9, "units": 5}
        assert not second.created and second.updated == 0
        assert counts(db) == before and sorted(db.scalars(select(Resource.id))) == ids
        assert set(db.scalars(select(Resource.verification_status))) == {"pending"}
        unit = db.scalar(select(Resource).where(Resource.title == "Lecture videos"))
        assert (unit.format, unit.source_connector, unit.license) == ("video", "mit_ocw", "CC-BY-NC-SA-4.0")


def test_a_taken_down_source_stays_rejected(app, client):
    with app.state.database.sessions() as db:
        upsert_records(db, [record()], connector="manual_yaml", now=NOW)
        row = db.scalar(select(Resource))
        row.verification_status = "rejected"
        db.commit()
        report = upsert_records(
            db, [record(title="Use case diagram (UML)")], connector="manual_yaml", now=NOW
        )
        db.commit()
        db.refresh(row)
        # ADR 004 section 8.3: metadata may follow the file, the status never resets.
        assert (row.verification_status, row.title) == ("rejected", "Use case diagram (UML)")
        assert report.updated and not report.created


def test_invalid_records_are_counted_and_never_stored(app, client):
    with app.state.database.sessions() as db:
        report = upsert_records(
            db,
            [record(license="CC-BY-ND-4.0"), record(url="https://www.chegg.com/x")],
            connector="manual_yaml",
            now=NOW,
        )
        assert report.skipped == {"unknown_license": 1, "blocked_domain": 1}
        assert counts(db)["Resource"] == 0


def test_curated_labels_follow_the_file(app, client):
    def labels(db):
        return set(db.scalars(select(ResourceSubject.subject_id)))

    with app.state.database.sessions() as db:
        both = record(subjects=("ct.use-cases", "ct.requirements"))
        upsert_records(db, [both], connector="manual_yaml", now=NOW)
        assert labels(db) == {"ct.use-cases", "ct.requirements"}
        upsert_records(db, [record()], connector="manual_yaml", now=NOW)
        assert labels(db) == {"ct.use-cases"}


def test_rows_of_web_search_keep_their_metadata_and_status(app, client):
    url = "https://en.wikipedia.org/wiki/Use_case_diagram"
    with app.state.database.sessions() as db:
        db.add(Resource(url=url, canonical_url=url, title="Found by web search",
                        verification_status="verified"))
        db.flush()
        upsert_records(db, [record()], connector="manual_yaml", now=NOW)
        row = db.scalar(select(Resource))
        assert (row.title, row.verification_status, row.source_connector) == (
            "Found by web search", "verified", None)
        # The reviewer's label still applies: it describes the page, not the row.
        assert set(db.scalars(select(ResourceSubject.subject_id))) == {"ct.use-cases"}


def test_a_failing_provider_is_reported_and_its_staged_rows_are_tagged(app, client):
    class Broken:
        name = "manual_yaml"

        def fetch(self, subjects, since=None):
            yield record(subjects=())
            raise ConnectorError("index_timeout")

    with app.state.database.sessions() as db:
        report = ingest(db, Broken(), ["ct.use-cases"], now=NOW)
        assert (report.error, report.records, report.created["resources"]) == ("index_timeout", 1, 1)
        row = db.scalar(select(Resource))
        tags = db.scalars(select(ResourceSubject.subject_id).where(ResourceSubject.resource_id == row.id))
        assert "ct.use-cases" in set(tags)


def test_every_csc10014_node_has_five_candidates_from_the_hand_lists(app, client):
    """Done-when 3, offline part: the reviewed hand lists alone cover CSC10014."""
    subjects = sorted(set().union(*(labels for _, labels in node_subjects(demand()))))
    with app.state.database.sessions() as db:
        for name in ("manual_yaml", "open_yale"):
            report = ingest(db, connector(name, FakeFetcher({})), subjects, now=NOW)
            assert report.error is None and not report.skipped
        result = node_candidates(db, demand())
    assert len(result) == 7
    assert [(title, n) for title, n in result if n < 5] == []
