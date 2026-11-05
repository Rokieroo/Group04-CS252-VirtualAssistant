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
    print(f"[ OK ] {label}: {len(tables)} bảng ({', '.join(tables)})")
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
        "[ OK ] Không thấy secret trong các file git đang theo dõi."
        if not hits
        else f"{hits} vấn đề."
    )
    return 1 if hits else 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("db", help="Database & Security: schema cục bộ và quét secret")
    db_sub = p.add_subparsers(dest="db_command", required=True)

    seed = db_sub.add_parser("seed-institutions", help="nạp registry ROR/OpenAlex vào DB (idempotent)")
    seed.add_argument("--file", default=str(ROOT / "data/catalog/institutions.csv"))
    seed.set_defaults(func=_seed_institutions)

    init = db_sub.add_parser(
        "init", help="tạo database từ db/schema.sql (mặc định theo DATABASE_URL)"
    )
    init.add_argument("--db", help="ghi đè bằng một file SQLite cục bộ (tùy chọn)")
    init.add_argument(
        "--reset", action="store_true", help="xóa database cũ trước khi tạo"
    )
    init.set_defaults(func=_init)

    scan = db_sub.add_parser(
        "scan-secrets", help="tìm API key, token, private key trong repo"
    )
    scan.set_defaults(func=_scan)


def _seed_institutions(args):
    from app.catalog.institutions import read_registry, seed_institutions
    from app.db import session_scope
    rows = read_registry(args.file)
    with session_scope() as db:
        count = seed_institutions(db, rows)
    print(f"[ OK ] {count} institutions")
    return 0
