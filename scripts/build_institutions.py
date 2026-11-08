"""Build #96 offline from versioned snapshots, or download CC0 source snapshots.

References: https://ror.readme.io/docs/zenodo and
https://help.openalex.org/data/institutions/ . Never reads an application .env/key.
"""

import argparse
import gzip
import hashlib
import json
import ssl
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.catalog.institutions import build_registry, write_registry


def download(directory):
    import httpx
    import truststore

    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        follow_redirects=True,
        timeout=120,
        headers={"User-Agent": "Pathly-CS252/0.3 (CC0 institution metadata)"},
    ) as client:
        response = client.get("https://zenodo.org/api/records/6347574")
        response.raise_for_status()
        meta = response.json()
        archive = next(f for f in meta["files"] if f["key"].endswith(".zip"))
        target = directory / "ror.zip"
        digest = hashlib.md5()
        if target.exists():
            digest.update(target.read_bytes())
        if not target.exists() or "md5:" + digest.hexdigest() != archive["checksum"]:
            digest = hashlib.md5()
            with (
                client.stream("GET", archive["links"]["self"]) as response,
                target.open("wb") as stream,
            ):
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    stream.write(chunk)
                    digest.update(chunk)
        if "md5:" + digest.hexdigest() != archive["checksum"]:
            raise ValueError("ror_checksum_mismatch")
        with zipfile.ZipFile(target) as zipped:
            name = next(
                n
                for n in zipped.namelist()
                if n.endswith(".json") and "schema_v1" not in n
            )
            (directory / "ror.json").write_bytes(zipped.read(name))
        rows, page = [], 1
        while True:
            response = client.get(
                "https://api.openalex.org/institutions",
                params={
                    "filter": "type:education,works_count:>999,has_ror:true",
                    "sort": "summary_stats.h_index:desc,cited_by_count:desc",
                    "per_page": 200,
                    "page": page,
                },
            )
            response.raise_for_status()
            payload = response.json()
            rows.extend(payload["results"])
            if not payload["results"] or len(rows) >= payload["meta"]["count"]:
                break
            # Basic paging is public; cursor paging requires an OpenAlex API key.
            # Fetch beyond 500 so all tied boundary scores are sorted locally.
            if len(rows) >= 2000:
                break
            page += 1
            time.sleep(0.11)
        (directory / "openalex.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8"
        )
        manifest = {
            "snapshot_date": datetime.now(UTC).date().isoformat(),
            "openalex_version": "sha256:"
            + hashlib.sha256((directory / "openalex.json").read_bytes()).hexdigest(),
            "ror_version": meta["doi"],
            "ror_checksum": archive["checksum"],
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        print(f"Downloaded {len(rows)} OpenAlex records; ROR {meta['doi']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--overrides", type=Path, default=Path("data/catalog/institutions-vn.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/catalog/institutions.csv")
    )
    parser.add_argument("--allowlist", type=Path)
    args = parser.parse_args()
    if args.download:
        download(args.snapshots)
    manifest = json.loads(
        (args.snapshots / "manifest.json").read_text(encoding="utf-8")
    )

    def read_snapshot(name):
        path = args.snapshots / (name + ".json")
        content = (
            path.read_bytes()
            if path.exists()
            else gzip.decompress(path.with_suffix(".json.gz").read_bytes())
        )
        return json.loads(content)

    overrides = (
        json.loads(args.overrides.read_text(encoding="utf-8"))
        if args.overrides.exists()
        else []
    )
    rows = build_registry(
        read_snapshot("openalex"),
        read_snapshot("ror"),
        **{
            k: manifest[k] for k in ("snapshot_date", "openalex_version", "ror_version")
        },
        overrides=overrides,
        limit=args.limit,
    )
    # ADR 004 section 4: a hand-picked row counts only once two people approved it.
    pending = sorted(o["ror_id"] for o in overrides if len(o.get("reviewers", [])) < 2)
    if pending:
        print(f"{len(pending)} manual institutions wait for 2 reviewers: {', '.join(pending)}")
    write_registry(rows, args.output)
    if args.allowlist:
        previous = args.allowlist.read_text(encoding="utf-8")
        domains = {
            line.strip() for line in previous.splitlines() if not line.startswith("#")
        }
        additions = sorted({r["domain"] for r in rows if int(r["tier"]) == 1} - domains)
        args.allowlist.write_text(
            previous.rstrip() + "\n" + "\n".join(additions) + "\n", encoding="utf-8"
        )
    print(f"Wrote {len(rows)} institutions to {args.output}")


if __name__ == "__main__":
    main()
