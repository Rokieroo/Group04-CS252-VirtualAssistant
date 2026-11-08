"""Developer CLI:  python dev.py <ui|ai|db|qa|devops> <command>

Run `python dev.py --help` or `python dev.py <domain> --help` for the full list.
"""
from __future__ import annotations

import argparse
import sys

from devcli import ai, db, devops, qa, ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="CLI phát triển dự án, chia theo 5 mảng: ui, ai, db, qa, devops.",
    )
    sub = parser.add_subparsers(dest="domain", required=True)
    for module in (ui, ai, db, qa, devops):
        module.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Piped/redirected output on Windows defaults to cp1252, which turns Vietnamese into "?".
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra and not getattr(args, "pass_extra", False):
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
