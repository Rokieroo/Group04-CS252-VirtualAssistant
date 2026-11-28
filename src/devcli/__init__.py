"""Developer CLI: one command group per development domain (ui, ai, db, qa, devops)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _terminate_tree(proc: subprocess.Popen) -> None:
    """Stop a child and everything it started (e.g. pnpm -> vite) after Ctrl+C."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # The child runs in its own process group, so Ctrl+C reached neither it nor its children.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        # The terminal already sent SIGINT to the whole foreground group; this covers a child ignoring it.
        proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    """Run a command, stream its output, and return its exit code."""
    print(f"$ {' '.join(cmd)}")
    try:
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))}
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags)
    except FileNotFoundError:
        print(f"Command '{cmd[0]}' not found. Please install it first (see README).", file=sys.stderr)
        return 127
    try:
        return proc.wait()
    except KeyboardInterrupt:
        _terminate_tree(proc)
        return 130
