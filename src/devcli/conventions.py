"""Branch and commit naming rules from docs/guidelines/ (GIT_WORKFLOW.md, COMMIT_CONVENTION.md)."""
from __future__ import annotations

import re

ROLES = ("uiux", "ai", "dbsec", "qa", "devops", "pm")
COMMIT_TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "chore", "ci")

# <role>-<name>/<issue>-<short-task>, e.g. ai-minh/12-item-generation
BRANCH_RE = re.compile(rf"^(?:{'|'.join(ROLES)})-[a-z0-9]+/\d+-[a-z0-9]+(?:-[a-z0-9]+)*$")
LONG_LIVED = {"main", "dev"}
BOT_PREFIXES = ("claude/", "codex/", "dependabot/")

# <type>(<scope>): <description>, scope optional, "!" marks a breaking change
COMMIT_RE = re.compile(rf"^(?:{'|'.join(COMMIT_TYPES)})(?:\([a-z0-9-]+\))?!?: \S.*$")
MAX_SUBJECT = 100


def check_branch(name: str) -> str | None:
    """Return None if the branch name is valid, else the reason it is not."""
    if name in LONG_LIVED or name.startswith(BOT_PREFIXES):
        return None
    if BRANCH_RE.match(name):
        return None
    return (
        f"'{name}' does not match <role>-<name>/<issue>-<task>. "
        f"Valid roles: {', '.join(ROLES)}. Example: ai-minh/12-item-generation"
    )


def check_commit(message: str) -> str | None:
    """Return None if the first line of a commit message is valid, else the reason."""
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    subject = lines[0].strip() if lines else ""
    if subject.startswith(("Merge ", "Revert ")):
        return None
    if not subject:
        return "Commit message is empty."
    if len(subject) > MAX_SUBJECT:
        return f"Subject line is {len(subject)} characters long, maximum is {MAX_SUBJECT}."
    if not COMMIT_RE.match(subject):
        return (
            f"'{subject}' does not match <type>(<scope>): <description>. "
            f"Valid types: {', '.join(COMMIT_TYPES)}. Example: feat(ai): add item generation prompt"
        )
    return None
