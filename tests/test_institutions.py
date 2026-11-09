"""Issue #96 done-when: a reproducible ROR/OpenAlex registry is the authority signal."""

import gzip
import json
from pathlib import Path

from sqlalchemy import select
from test_role_catalog import add_resource

from app.catalog.institutions import build_registry, read_registry, write_registry
from app.catalog.matching import match_sources
from app.vetting.policy import DomainPolicy, DomainTier, default_policy
from app.vetting.score import authority
from assistant.backend.catalog_models import Institution
from assistant.backend.catalog_repository import verified_resources

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog"
SNAPSHOTS = CATALOG / "institution-snapshots"


def test_the_bundled_snapshot_rebuilds_the_registry_byte_for_byte(tmp_path):
    manifest = json.loads((SNAPSHOTS / "manifest.json").read_text(encoding="utf-8"))

    def snapshot(name):
        return json.loads(gzip.decompress((SNAPSHOTS / f"{name}.json.gz").read_bytes()))

    rows = build_registry(
        snapshot("openalex"),
        snapshot("ror"),
        snapshot_date=manifest["snapshot_date"],
        openalex_version=manifest["openalex_version"],
        ror_version=manifest["ror_version"],
        overrides=json.loads((CATALOG / "institutions-vn.json").read_text(encoding="utf-8")),
    )
    write_registry(rows, tmp_path / "institutions.csv")
    assert (tmp_path / "institutions.csv").read_bytes() == (
        CATALOG / "institutions.csv"
    ).read_bytes()


def test_every_row_has_an_identifier_a_domain_and_its_snapshot_versions():
    rows = read_registry(CATALOG / "institutions.csv")
    assert len(rows) >= 500
    for row in rows:
        assert row["ror_id"].startswith(("https://ror.org/", "vn-k12:")) and row["domain"]
        signal = json.loads(row["rank_signal"])
        assert signal["snapshot_date"] and signal["openalex_version"]


def test_unreviewed_manual_institutions_never_become_authoritative():
    options = {"snapshot_date": "d", "openalex_version": "o", "ror_version": "r"}
    pick = {"ror_id": "vn-k12:moet", "name": "MOET", "country": "VN",
            "domain": "moet.gov.vn", "tier": 1, "reason": "official"}
    assert build_registry([], [], **options, overrides=[{**pick, "reviewers": ["a"]}]) == []
    (row,) = build_registry([], [], **options, overrides=[{**pick, "reviewers": ["b", "a"]}])
    assert json.loads(row["rank_signal"])["reviewers"] == ["a", "b"]


def test_web_vetting_authority_comes_from_the_institution_tier(tmp_path):
    registry = tmp_path / "institutions.csv"
    write_registry(
        [
            {"ror_id": "https://ror.org/01", "name": "A", "name_vi": "", "country": "VN",
             "domain": "a.edu.vn", "tier": 2, "rank_signal": "{}"},
            {"ror_id": "https://ror.org/02", "name": "B", "name_vi": "", "country": "US",
             "domain": "b.edu", "tier": 3, "rank_signal": "{}"},
        ],
        registry,
    )
    (tmp_path / "blocklist.txt").write_text("bad.a.edu.vn\n", encoding="utf-8")
    policy = DomainPolicy.load(tmp_path, registry=registry)
    assert policy.tier("https://cs.a.edu.vn/notes") == DomainTier.TIER2
    assert authority(policy.tier("https://cs.a.edu.vn/notes")) == 0.7
    assert policy.tier("https://a.edu.vn.evil.example/") == DomainTier.OTHER
    assert policy.tier("https://b.edu/") == DomainTier.OTHER  # tier 3 earns nothing
    assert policy.tier("https://bad.a.edu.vn/") == DomainTier.BLOCKED
    assert DomainPolicy.load(tmp_path).tier("https://cs.a.edu.vn/") == DomainTier.OTHER
    # The shipped policy reads the shipped registry.
    first = read_registry(CATALOG / "institutions.csv")[0]
    assert default_policy().tier("https://" + first["domain"]) == DomainTier(first["tier"])


def test_catalog_authority_follows_the_institution_tier(app, client, clock):
    with app.state.database.sessions() as db:
        resource = add_resource(db, clock[0])
        # Not .edu: the allowlist already ranks every .edu host tier 1 (ADR 004: best wins).
        resource.url = resource.canonical_url = "https://source0.org/solution-ladder"
        resource.domain = "source0.org"
        institution = db.scalar(select(Institution).where(Institution.domain == "source0.edu"))
        institution.domain = "source0.org"
        db.flush()
        node = {"title": "Solution ladder", "language": "en", "level": "undergrad",
                "subjects": ["ct.ladder"]}

        def matched_authority():
            (row,) = [r for r in verified_resources(db, clock[0]) if r["id"] == resource.id]
            (match,) = match_sources(node, [row])
            return row["tier"], match["breakdown"]["authority"]

        assert matched_authority() == (1, 1.0)
        institution.tier = 2
        db.flush()
        assert matched_authority() == (2, 0.7)


def test_match_sources_handles_missing_keys():
    # Node with 'lang' alias and omitted level
    node = {
        "title": "Recursion Intro",
        "lang": "en",
        "subjects": ["ct.recursion"],
    }
    # Resource with missing optional fields (domain, format)
    resource = {
        "id": "r1",
        "title": "Recursion Guide",
        "verification_status": "verified",
        "subjects": ["ct.recursion"],
        "lang": "en",
        "level": "undergrad",
        "tier": 1,
        "is_free": True,
    }
    matches = match_sources(node, [resource])
    assert len(matches) == 1
    assert matches[0]["id"] == "r1"
