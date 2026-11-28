"""Developer CLI: one command group per development domain (ui, ai, db, qa, devops)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _terminate_tree(proc: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    """Terminate a child process and its descendants cleanly on interrupt."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            proc.kill()
    else:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    try:
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    """Run a command, stream its output, and return its exit code."""
    print(f"$ {' '.join(cmd)}")
    try:
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))}
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags)
    except FileNotFoundError:
        print(f"Không tìm thấy lệnh '{cmd[0]}'. Hãy cài đặt nó trước (xem README).", file=sys.stderr)
        return 127
    try:
        return proc.wait()
    except KeyboardInterrupt:
        _terminate_tree(proc)
        return 130
