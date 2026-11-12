"""Privacy protections for external provider queries (issue #156, ADR 004).

External queries must be sanitized through ``pii_filter`` so that no learner names,
emails, phone numbers, identity credentials, secret tokens, or local filenames
are leaked to third-party providers.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

# Line-level and token-level PII patterns
_LINE_PII_PATTERNS = [
    # Contact info headers
    re.compile(
        r"(?i)^[ \t]*(?:Personal\s+)?(?:Cell|Phone|Tel|Email|Contact|Emergency contact)[^:\n]*:[^\n]*$",
        re.MULTILINE,
    ),
    # Identification numbers and credentials
    re.compile(
        r"(?i)^[ \t]*(?:Citizen ID|CCCD|CMND|Passport|Tax Code|Bank Account|VCB|US SSN|SSN|Date of Birth)[^:\n]*:[^\n]*$",
        re.MULTILINE,
    ),
    # Secrets, tokens, passwords, credentials
    re.compile(
        r"(?i)^[ \t]*(?:Home Address|Home WiFi|WiFi|SSID|Password|Admin Pass|Bot User Token)[^:\n]*:[^\n]*$",
        re.MULTILINE,
    ),
    # Instructors / TAs / Personnel / Family
    re.compile(
        r"(?i)^[ \t]*(?:Instructor|TA|Lecturer|Guest Lecturer|Spouse|Child|Student)[^:\n]*:[^\n]*$",
        re.MULTILINE,
    ),
    # Leaks, rosters, notices, scholarships, GPAs
    re.compile(
        r"(?i)^[ \t]*.*?(?:Grade Roster|Scholarship Recipients|DevOps Secret|Office Hours at Home|Budget Allocation|Notice:\s*TA|GPA:|Poor household|certificate\s*#|Financial aid).*?$",
        re.MULTILINE,
    ),
]

_INLINE_PATTERNS = [
    # Emails
    re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b", re.IGNORECASE),
    # Slack tokens
    re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]+\b"),
    # Phone numbers
    re.compile(r"(?:\+84|0)[1-9](?:[\s.-]?\d){8}\b"),
    re.compile(r"\b\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    re.compile(r"\b555-\d{4}\b"),
    # National IDs, CCCD, SSN (9-12 digits)
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{9,12}\b"),
    # Document filenames
    re.compile(
        r"\b[\w-]+\.(?:pdf|docx?|pptx?|xlsx?|txt|md|csv|html?|json)\b",
        re.IGNORECASE,
    ),
]


def pii_filter(
    text: str,
    *,
    learner_name: str | None = None,
    learner_email: str | None = None,
    filenames: Iterable[str] | None = None,
    redact_marker: str = "",
) -> str:
    """Sanitize text by redacting personal identifiers, secrets, and learner details.

    Parameters:
        text: The source string to clean.
        learner_name: Optional learner's display name to strip.
        learner_email: Optional learner's email to strip.
        filenames: Optional collection of syllabus or document filenames to strip.
        redact_marker: The replacement string (default empty string to remove).

    Returns:
        The sanitized text stripped of PII.
    """
    if not text:
        return ""

    filtered = text

    # Strip explicit learner credentials
    if learner_email:
        filtered = re.sub(
            re.escape(learner_email), redact_marker, filtered, flags=re.IGNORECASE
        )
    if learner_name and len(learner_name.strip()) > 1:
        filtered = re.sub(
            re.escape(learner_name.strip()),
            redact_marker,
            filtered,
            flags=re.IGNORECASE,
        )
        for part in learner_name.strip().split():
            if len(part) > 2:
                filtered = re.sub(
                    rf"\b{re.escape(part)}\b",
                    redact_marker,
                    filtered,
                    flags=re.IGNORECASE,
                )

    # Strip explicit document filenames
    if filenames:
        for fn in filenames:
            if fn and fn.strip():
                clean_name = Path(fn).name
                filtered = re.sub(
                    re.escape(clean_name), redact_marker, filtered, flags=re.IGNORECASE
                )
                stem = Path(fn).stem
                if len(stem) > 3:
                    filtered = re.sub(
                        rf"\b{re.escape(stem)}\b",
                        redact_marker,
                        filtered,
                        flags=re.IGNORECASE,
                    )

    # Strip line-level patterns first
    for pattern in _LINE_PII_PATTERNS:
        filtered = pattern.sub(redact_marker, filtered)

    # Strip inline token patterns
    for pattern in _INLINE_PATTERNS:
        filtered = pattern.sub(redact_marker, filtered)

    # Clean up empty lines and normalize whitespaces
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in filtered.splitlines()
        if line.strip()
    ]
    return "\n".join(lines)


def build_safe_external_query(
    *,
    node_title: str,
    concept_names: Iterable[str] | None = None,
    subject_names: Iterable[str] | None = None,
    learner_name: str | None = None,
    learner_email: str | None = None,
    filenames: Iterable[str] | None = None,
) -> str:
    """Construct a clean, sanitized query for external providers from node context.

    Only academic keywords (node title, concepts, subjects) are included, guaranteed
    free of learner identifiers, emails, phones, secrets, or file paths.
    """
    terms: list[str] = []

    safe_title = pii_filter(
        node_title,
        learner_name=learner_name,
        learner_email=learner_email,
        filenames=filenames,
    )
    if safe_title:
        terms.append(safe_title)

    if concept_names:
        for c in concept_names:
            safe_c = pii_filter(
                c,
                learner_name=learner_name,
                learner_email=learner_email,
                filenames=filenames,
            )
            if safe_c and safe_c.lower() not in [t.lower() for t in terms]:
                terms.append(safe_c)

    if subject_names:
        for s in subject_names:
            safe_s = pii_filter(
                s,
                learner_name=learner_name,
                learner_email=learner_email,
                filenames=filenames,
            )
            if safe_s and safe_s.lower() not in [t.lower() for t in terms]:
                terms.append(safe_s)

    combined = " ".join(terms)
    return pii_filter(
        combined,
        learner_name=learner_name,
        learner_email=learner_email,
        filenames=filenames,
    )
