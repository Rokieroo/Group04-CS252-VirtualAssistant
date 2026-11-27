"""UI/UX commands: wrap the frontend scripts in ui/."""
from __future__ import annotations

import argparse
import shutil

from devcli import ROOT, run

UI_DIR = ROOT / "ui"
SCRIPTS = {
    "install": ["install"],
    "dev": ["run", "dev"],
    "build": ["run", "build"],
    "test": ["test"],
    "e2e": ["run", "test:e2e"],
}


def _pkg_manager() -> list[str]:
    """Prefer pnpm (direct or via corepack) to match ui/pnpm-lock.yaml."""
    pnpm = shutil.which("pnpm")
    if pnpm:
        return [pnpm]
    corepack = shutil.which("corepack")
    if corepack:
        return [corepack, "pnpm"]
    return [shutil.which("npm") or "npm"]


def _npm(args: argparse.Namespace) -> int:
    if not (UI_DIR / "package.json").exists():
        print(
            "ui/ does not have package.json yet. Merge the frontend React + Vite branch first."
        )
        return 1
    cmd = _pkg_manager()
    return run([*cmd, *SCRIPTS[args.action]], cwd=UI_DIR)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ui", help="UI/UX: install, run, build, and test frontend")
    p.add_argument("action", choices=sorted(SCRIPTS), help="install | dev | build | test | e2e")
    p.set_defaults(func=_npm)
