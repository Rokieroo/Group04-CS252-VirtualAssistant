"""Reproducible authority registry using ADR 004's OpenAlex/ROR ordering (#96)."""

import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from app.vetting.policy import DomainTier
from app.vetting.score import authority

FIELDS = ("ror_id", "name", "name_vi", "country", "domain", "tier", "rank_signal")


def domain_of(url):
    host = urlsplit(url if "://" in url else "https://" + url).hostname or ""
    return host.lower().rstrip(".").removeprefix("www.")


def matches_domain(host, domain):
    host, domain = domain_of(host), domain_of(domain)
    return bool(domain) and (host == domain or host.endswith("." + domain))


def authority_for(host, institutions):
    tiers = [
        int(row["tier"]) for row in institutions if matches_domain(host, row["domain"])
    ]
    return authority(DomainTier(min(tiers, default=3)))


def build_registry(
    openalex,
    ror,
    *,
    snapshot_date,
    openalex_version,
    ror_version,
    overrides=(),
    limit=500,
):
    """Never derive publication versions/dates from the machine clock.

    Join only active ROR records. Homepage/domain disagreement is rejected; suffix
    comparisons require a dot boundary, so mit.edu.evil.example never matches MIT.
    """
    registry = {
        row["id"]: row for row in ror if row.get("status", "active") == "active"
    }
    eligible = []
    for row in openalex:
        org = registry.get(row.get("ror"))
        if (
            row.get("type") != "education"
            or row.get("works_count", 0) < 1000
            or not org
            or not row.get("homepage_url")
        ):
            continue
        domains = sorted(
            set(
                org.get("domains")
                or [
                    domain_of(link["value"])
                    for link in org.get("links", [])
                    if link.get("type") == "website"
                ]
            )
        )
        homepage = domain_of(row["homepage_url"])
        if not any(
            matches_domain(homepage, d) or matches_domain(d, homepage) for d in domains
        ):
            continue
        eligible.append((row, domains))
    eligible.sort(
        key=lambda pair: (
            -pair[0].get("summary_stats", {}).get("h_index", 0),
            -pair[0].get("cited_by_count", 0),
            pair[0]["id"],
        )
    )
    results = {}
    for rank, (row, domains) in enumerate(eligible[:limit], 1):
        signals = {
            "rank": rank,
            "h_index": row.get("summary_stats", {}).get("h_index", 0),
            "cited_by_count": row.get("cited_by_count", 0),
            "works_count": row["works_count"],
            "openalex_id": row["id"],
            "snapshot_date": snapshot_date,
            "openalex_version": openalex_version,
            "ror_version": ror_version,
            "domains": domains,
        }
        results[row["ror"]] = {
            "ror_id": row["ror"],
            "name": row["display_name"],
            "name_vi": "",
            "country": row.get("country_code") or "",
            "domain": domain_of(row["homepage_url"]),
            "tier": 1 if rank <= 500 else 2 if rank <= 2000 else 3,
            "rank_signal": json.dumps(signals, ensure_ascii=False, sort_keys=True),
        }
    for override in sorted(overrides, key=lambda r: r["ror_id"]):
        identifier = override["ror_id"]
        if not identifier.startswith("vn-k12:") and identifier not in registry:
            raise ValueError("manual_institution_missing_ror: " + identifier)
        if len(override.get("reviewers", [])) < 2:
            # Unreviewed institutional boosts must never silently become authoritative.
            continue
        result = {k: override.get(k, "") for k in FIELDS}
        result["rank_signal"] = json.dumps(
            {
                "manual": True,
                "reason": override["reason"],
                "reviewers": sorted(override["reviewers"]),
                "snapshot_date": snapshot_date,
                "openalex_version": openalex_version,
                "ror_version": ror_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        results[identifier] = result
    return sorted(results.values(), key=lambda row: (int(row["tier"]), row["ror_id"]))


def write_registry(rows, path):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_registry(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    seen = set()
    for row in rows:
        if not row["ror_id"] or not row["domain"] or row["ror_id"] in seen:
            raise ValueError("invalid_or_duplicate_institution")
        row["tier"] = int(row["tier"])
        if row["tier"] not in {1, 2, 3}:
            raise ValueError("invalid_institution_tier")
        json.loads(row["rank_signal"])
        seen.add(row["ror_id"])
    return rows


def seed_institutions(db, rows):
    """Portable upsert without importing the backend ORM into the app layer."""
    from sqlalchemy import text

    for row in rows:
        row = {**row, "id": str(uuid5(NAMESPACE_URL, row["ror_id"]))}
        existing = db.scalar(
            text("SELECT id FROM institutions WHERE ror_id=:ror_id"), row
        )
        if existing:
            db.execute(
                text(
                    "UPDATE institutions SET name=:name, name_vi=:name_vi, country=:country, "
                    "domain=:domain, tier=:tier, rank_signal=:rank_signal WHERE ror_id=:ror_id"
                ),
                row,
            )
        else:
            db.execute(
                text(
                    "INSERT INTO institutions (id, ror_id, name, name_vi, country, domain, tier, "
                    "rank_signal) VALUES (:id,:ror_id,:name,:name_vi,:country,:domain,:tier,:rank_signal)"
                ),
                row,
            )
    return len(rows)
