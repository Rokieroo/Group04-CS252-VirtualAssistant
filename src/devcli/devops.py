"""DevOps commands: environment check, local CI, naming rules and git hooks."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from devcli import ROOT, run
from devcli.conventions import check_branch, check_commit

HOOK = """#!/bin/sh
# Installed by: python dev.py devops install-hooks
python dev.py devops commit-msg --file "$1"
"""


def _check(args: argparse.Namespace) -> int:
    return run([sys.executable, "scripts/check_env.py"])


def _ci(args: argparse.Namespace) -> int:
    steps = [
        ["-m", "ruff", "check", "."],
        ["-m", "pytest", "tests/"],
        ["dev.py", "db", "scan-secrets"],
        ["dev.py", "ai", "benchmark", "validate"],
    ]
    failed = []
    for step in steps:
        if run([sys.executable, *step]) != 0:
            failed.append(" ".join(step))
    print("[ OK ] Local CI passed." if not failed else f"[FAIL] Failed step(s): {', '.join(failed)}")
    return 1 if failed else 0


def _branch(args: argparse.Namespace) -> int:
    name = args.name or subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    problem = check_branch(name)
    print(f"[FAIL] {problem}" if problem else f"[ OK ] Valid branch name: {name}")
    return 1 if problem else 0


def _commit_msg(args: argparse.Namespace) -> int:
    message = Path(args.file).read_text(encoding="utf-8") if args.file else " ".join(args.message)
    problem = check_commit(message)
    print(f"[FAIL] {problem}" if problem else "[ OK ] Valid commit message.")
    return 1 if problem else 0


def _install_hooks(args: argparse.Namespace) -> int:
    hook = ROOT / ".git" / "hooks" / "commit-msg"
    if not hook.parent.exists():
        print(".git/hooks not found. Run this command inside a cloned repository.")
        return 1
    hook.write_text(HOOK, encoding="utf-8")
    hook.chmod(0o755)
    print(f"[ OK ] Installed {hook.relative_to(ROOT)}: invalid commit messages will be blocked.")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("devops", help="DevOps: environment check, local CI, branch/commit rules")
    ops = p.add_subparsers(dest="devops_command", required=True)

    ops.add_parser("check", help="run scripts/check_env.py").set_defaults(func=_check)
    ops.add_parser("ci", help="run lint + tests + secret scan + benchmark validation").set_defaults(func=_ci)

    branch = ops.add_parser("branch", help="validate branch name (default: current branch)")
    branch.add_argument("name", nargs="?")
    branch.set_defaults(func=_branch)

    msg = ops.add_parser("commit-msg", help="validate commit message syntax")
    msg.add_argument("message", nargs="*")
    msg.add_argument("--file", help="read message from file (for git hooks)")
    msg.set_defaults(func=_commit_msg)

    ops.add_parser("install-hooks", help="install commit-msg git hook").set_defaults(func=_install_hooks)
