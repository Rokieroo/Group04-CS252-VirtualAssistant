"""Database and Security commands: local schema and a secret scan."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from devcli import ROOT

LOCAL_DB = ROOT / "data" / "local.db"

SECRET_PATTERNS = {
    # \b keeps words like "risk-management-framework" in URLs from matching
    "OpenAI key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def init_db(path: Path, reset: bool = False) -> list[str]:
    """Create the schema in a SQLite file and return the table names."""
    from app.db import init_db as init_database

    database_url = f"sqlite:///{Path(path).resolve().as_posix()}"
    return init_database(reset=reset, database_url=database_url)


def scan_text(text: str) -> list[str]:
    """Return the names of secret patterns found in text."""
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout
    return [ROOT / line for line in out.splitlines() if line]


def _init(args: argparse.Namespace) -> int:
    from app.db import get_database_url
    from app.db import init_db as init_database

    if args.db:
        path = Path(args.db)
        database_url = f"sqlite:///{path.resolve().as_posix()}"
        label = path
    else:
        database_url = get_database_url()
        label = database_url

    tables = init_database(reset=args.reset, database_url=database_url)
    print(f"[ OK ] {label}: {len(tables)} tables ({', '.join(tables)})")
    return 0


def _scan(args: argparse.Namespace) -> int:
    hits = 0
    safe_env_examples = {".env.example", ".env.sample", ".env.template"}
    for file in tracked_files():
        if not file.is_file() or file.suffix in {
            ".png",
            ".jpg",
            ".pdf",
            ".db",
            ".sqlite",
            ".sqlite3",
            ".svg",
        }:
            continue
        found = scan_text(file.read_text(encoding="utf-8", errors="ignore"))
        if (
            file.name == ".env" or file.name.startswith(".env.")
        ) and file.name not in safe_env_examples:
            found.append(".env file is tracked by git")
        for name in found:
            hits += 1
            print(f"[FAIL] {file.relative_to(ROOT)}: {name}")
    print(
        "[ OK ] No secrets found in git-tracked files."
        if not hits
        else f"{hits} issue(s) found."
    )
    return 1 if hits else 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("db", help="Database & Security: local schema and secret scan")
    db_sub = p.add_subparsers(dest="db_command", required=True)

    seed = db_sub.add_parser("seed-institutions", help="load ROR/OpenAlex registry into DB (idempotent)")
    seed.add_argument("--file", default=str(ROOT / "data/catalog/institutions.csv"))
    seed.set_defaults(func=_seed_institutions)

    snapshot = db_sub.add_parser(
        "snapshot-catalog",
        help="export shared catalog (no user data) to a JSON file",
    )
    snapshot.add_argument("--out", required=True, help="output JSON file path")
    snapshot.set_defaults(func=_snapshot_catalog)

    catalog = db_sub.add_parser(
        "seed-catalog", help="load a catalog snapshot into DB (idempotent, merge by natural key)"
    )
    source = catalog.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="snapshot exported by `db snapshot-catalog`")
    source.add_argument(
        "--sample",
        action="store_true",
        help="bundled sample snapshot with sources for the CSC10014 roadmap; dev and CI only",
    )
    catalog.set_defaults(func=_seed_catalog)

    init = db_sub.add_parser(
        "init", help="create database from db/schema.sql (defaults to DATABASE_URL)"
    )
    init.add_argument("--db", help="override with a local SQLite file (optional)")
    init.add_argument(
        "--reset", action="store_true", help="reset existing database before creating tables"
    )
    init.set_defaults(func=_init)

    scan = db_sub.add_parser(
        "scan-secrets", help="scan tracked files for API keys, tokens, and private keys"
    )
    scan.set_defaults(func=_scan)


def _backend_database():
    """The backend database of DATABASE_URL (or .env), migrated to head."""
    from dotenv import load_dotenv

    from assistant.backend.config import Settings
    from assistant.backend.database import Database

    load_dotenv(ROOT / ".env")
    database = Database(Settings.from_env().database_url)
    database.create_schema()
    return database


def _snapshot_catalog(args: argparse.Namespace) -> int:
    from assistant.backend.catalog_snapshot import export_snapshot, write_snapshot
    from assistant.backend.models import utcnow

    database = _backend_database()
    with database.sessions() as db:
        snapshot = export_snapshot(db, utcnow())
    write_snapshot(Path(args.out), snapshot)
    counts = {name: len(rows) for name, rows in snapshot["tables"].items()}
    print(f"[ OK ] {args.out}: {counts}")
    return 0


def _seed_catalog(args: argparse.Namespace) -> int:
    from assistant.backend.catalog_snapshot import SAMPLE, load_snapshot, read_snapshot
    from assistant.backend.models import utcnow

    path = SAMPLE if args.sample else Path(args.file)
    database = _backend_database()
    with database.sessions() as db:
        try:
            added = load_snapshot(
                db, read_snapshot(path), utcnow(), restamp_by="seed:sample" if args.sample else None
            )
        except ValueError as exc:
            print(f"[FAIL] {path}: {exc}")
            return 2
        db.commit()
    print(f"[ OK ] {path.name}: added {dict(added) or 'no new rows'}")
    return 0


def _seed_institutions(args):
    from app.catalog.institutions import read_registry, seed_institutions
    from app.db import session_scope
    rows = read_registry(args.file)
    with session_scope() as db:
        count = seed_institutions(db, rows)
    print(f"[ OK ] {count} institutions")
    return 0
