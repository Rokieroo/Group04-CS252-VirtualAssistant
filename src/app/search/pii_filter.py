"""PII filtering for search queries (spec 11.1 and safeguard 6).

Every query must pass through :func:`filter_pii` before it leaves the process:
syllabi can contain lecturer names, student names, email addresses, phone
numbers, and student IDs.  Search engines never need those values.
"""

from __future__ import annotations

import re

__all__ = ["contains_pii", "filter_pii"]

# Uppercase letters used by Vietnamese (including accented forms).  We avoid
# the broad ``A-ZÀ-Ỹ`` range because it also contains lowercase characters.
_VN_UPPER = (
    "A-Z"
    "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝ"
    "ĂĐĨŨƠƯ"
    "ẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ"
)
_NAME_WORD = rf"[{_VN_UPPER}][^\W\d_]*(?:-[{_VN_UPPER}][^\W\d_]*)*"
_NAME = rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,5}}"
_TITLE = r"(?i:(?:ThS|TS|PGS|GS|Dr|Prof|Mr|Mrs|Ms|Th\.S|PGS\.TS|GS\.TS)\.?\s+)"
_HONORIFIC_TITLE = (
    r"(?i:\b(?:Thầy|Cô|ThS|TS|PGS|GS|Dr|Prof|Mr|Mrs|Ms|Th\.S|PGS\.TS|GS\.TS)"
    r"\.?\s+)"
)

_EMAIL = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)

# Vietnamese mobile numbers start with 0 or +84; allow spaces, dots, and dashes
# commonly used in syllabi (090 123 4567, 090.123.4567, +84 90 123 4567).
_PHONE = re.compile(
    r"(?<![\w+])(?:\+?84|0)(?:[ .\-()]?\d){9,10}(?!\w)"
)

_ID_LABEL = re.compile(
    r"(?P<label>(?i:\b(?:mssv|mã\s*(?:số\s*)?sinh\s*viên|mã\s*sv|"
    r"student\s*(?:id|code|number)|sv\s*(?:id|code)|id)\b)"
    r"\s*[:：\-–—|*]?\s*)"
    r"(?P<value>[A-Za-z]{0,4}\d{5,12}[A-Za-z0-9]*)"
)

# Standalone student IDs are typically 7-12 digits.  Keep the range away from
# years (4 digits) and course codes (for example CSC10014, CS252).
_ID_GENERIC = re.compile(r"\b\d{7,12}\b")
_ID_PREFIXED = re.compile(r"\b[A-Za-z]{1,2}\d{6,10}\b")

_NAME_LABEL = re.compile(
    r"(?P<label>(?i:\b(?:"
    r"họ\s+(?:và\s+)?tên(?:\s+(?:sinh\s+viên|sv|giảng\s+viên|gv|giáo\s+viên))?|"
    r"họ\s+tên(?:\s+(?:sinh\s+viên|sv|giảng\s+viên|gv|giáo\s+viên))?|"
    r"tên(?:\s+(?:sinh\s+viên|sv|giảng\s+viên|gv|giáo\s+viên))?|"
    r"giảng\s+viên(?:\s+(?:phụ\s+trách|hướng\s+dẫn|chính|bộ\s+môn))?|"
    r"giáo\s+viên|"
    r"gv(?:\s*(?:hd|pt|chính))?|cbgd|"
    r"người\s+(?:hướng\s+dẫn|thực\s+hiện)|"
    r"sinh\s+viên(?:\s+(?:thực\s+hiện|thực\s+tập))?|sv|học\s+viên|"
    r"teacher(?:\s+name)?|instructor(?:\s+name)?|lecturer(?:\s+name)?|"
    r"student(?!\s+(?:id|code|number)\b)(?:\s+name)?|"
    r"full\s+name|name"
    r")\b))(?!\s+(?i:sv|sinh\s+viên|gv|giảng\s+viên|giáo\s+viên)\b)"
    r"\s*(?:[:：\-–—|*]\s*)?"
    rf"(?P<title>(?:{_TITLE})*)"
    rf"(?P<name>{_NAME})"
)

_HONORIFIC = re.compile(
    rf"(?P<title>(?:{_HONORIFIC_TITLE})+)(?P<name>{_NAME})"
)

# A bare Vietnamese name has no label to anchor it.  A short surname list plus
# the uppercase-word shape catches the common case without masking ordinary
# topic phrases (for example, "Problem framing" or "Do not...").
_SURNAME = (
    r"(?:Nguyễn|Nguyen|Trần|Tran|Lê|Le|Phạm|Pham|Hoàng|Hoang|Huỳnh|Huynh|"
    r"Phan|Vũ|Vu|Võ|Vo|Đặng|Dang|Bùi|Bui|Đỗ|Do|Hồ|Ho|Ngô|Ngo|Dương|Duong|"
    r"Lý|Ly|Đinh|Dinh|Trịnh|Trinh|Lưu|Luu|Trương|Truong|Tạ|Ta|Phùng|Phung|"
    r"Mai|Tô|Đoàn|Doan|Vương|Vuong|Lâm|Lam|Thái|Thai)"
)
_BARE_NAME = re.compile(
    rf"\b(?i:{_SURNAME})\s+{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,4}}\b"
)


def _mask_labeled_name(match: re.Match[str]) -> str:
    return f"{match.group('label')}[NAME]"


def _mask_honorific(match: re.Match[str]) -> str:
    return f"{match.group('title')}[NAME]"


def filter_pii(text: str) -> str:
    """Return ``text`` with emails, phones, names, and student IDs masked.

    Masking is intentionally conservative: it is always safe to remove a word
    from a search query, while leaking a student's identity is not.
    """

    if not text:
        return text
    cleaned = _EMAIL.sub("[EMAIL]", text)
    cleaned = _PHONE.sub("[PHONE]", cleaned)
    cleaned = _ID_LABEL.sub(lambda m: f"{m.group('label')}[STUDENT_ID]", cleaned)
    cleaned = _ID_GENERIC.sub("[STUDENT_ID]", cleaned)
    cleaned = _ID_PREFIXED.sub("[STUDENT_ID]", cleaned)
    cleaned = _NAME_LABEL.sub(_mask_labeled_name, cleaned)
    cleaned = _HONORIFIC.sub(_mask_honorific, cleaned)
    cleaned = _BARE_NAME.sub("[NAME]", cleaned)
    return cleaned


def contains_pii(text: str) -> bool:
    """Whether :func:`filter_pii` would change ``text``."""

    return bool(text) and filter_pii(text) != text
