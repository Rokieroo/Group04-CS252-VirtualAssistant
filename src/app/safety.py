"""Safety and crisis intervention filters (Issue #164, spec 11.4).

Detects self-harm and suicide ideation signals in user input across Vietnamese
and English, provides compassionate responses with verified Vietnamese emergency
and psychological support hotlines, and ensures raw sensitive crisis expressions
are never persisted in regular chat history.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "HOTLINES",
    "SAFE_REDACTION_MESSAGE",
    "build_crisis_reply",
    "is_crisis_message",
    "redact_crisis_content",
]

SAFE_REDACTION_MESSAGE = "[Nội dung đã được lọc vì lý do an toàn / Content filtered for safety]"

HOTLINES = (
    {
        "name": "Tổng đài Quốc gia Bảo vệ Trẻ em",
        "number": "111",
        "description": "Tư vấn tâm lý, bảo vệ trẻ em và thanh thiếu niên (Miễn phí 24/7)",
    },
    {
        "name": "Đường dây nóng Ngày Mai",
        "number": "096 306 1414",
        "description": "Hỗ trợ người trầm cảm và khủng hoảng tâm lý (13:00 - 20:30)",
    },
    {
        "name": "Cấp cứu Y tế Khẩn cấp",
        "number": "115",
        "description": "Cấp cứu y tế và can thiệp khẩn cấp (24/7)",
    },
)

# Vietnamese crisis regex patterns (accented and unaccented)
_VI_CRISIS_REGEXES = [
    r"\btự\s*tử\b",
    r"\btu\s*tu\b",
    r"\btự\s*sát\b",
    r"\btu\s*sat\b",
    r"\btự\s*vẫn\b",
    r"\btu\s*van\b",
    r"\bmuốn\s*chết\b",
    r"\bmuon\s*chet\b",
    r"\bchán\s*sống\b",
    r"\bchan\s*song\b",
    r"\bkhông\s*muốn\s*sống\b",
    r"\bkhong\s*muon\s*song\b",
    r"\bhết\s*muốn\s*sống\b",
    r"\bhet\s*muon\s*song\b",
    r"\bkết\s*liễu\s*(cuộc\s*đời|bản\s*thân)?\b",
    r"\bket\s*lieu\b",
    r"\bkết\s*thúc\s*(cuộc\s*sống|cuộc\s*đời|tất\s*cả)\b",
    r"\bket\s*thuc\s*(cuoc\s*song|cuoc\s*doi|tat\s*ca)\b",
    r"\bchấm\s*dứt\s*(cuộc\s*sống|cuộc\s*đời)\b",
    r"\bcham\s*dut\s*(cuoc\s*song|cuoc\s*doi)\b",
    r"\btự\s*hại\b",
    r"\btu\s*hai\b",
    r"\brạch\s*tay\b",
    r"\brach\s*tay\b",
    r"\bcắt\s*cổ\s*tay\b",
    r"\bcat\s*co\s*tay\b",
    r"\buống\s*thuốc\s*ngủ\s*tự\s*tử\b",
    r"\bnhảy\s*(cầu|lầu)\b",
    r"\bnhay\s*(cau|lau)\b",
    r"\btreo\s*cổ\b",
    r"\btreo\s*co\b",
]

# English crisis regex patterns
_EN_CRISIS_REGEXES = [
    r"\bsuicid(e|al)\b",
    r"\bkill(ing)?\s+myself\b",
    r"\bwant\s+to\s+die\b",
    r"\bend(ing)?\s+my\s+life\b",
    r"\btak(e|ing)\s+my\s+own\s+life\b",
    r"\bself[\s-]harm\b",
    r"\bcut(ting)?\s+myself\b",
    r"\bcut(ting)?\s+my\s+wrist(s)?\b",
    r"\bslit(ting)?\s+my\s+wrist(s)?\b",
    r"\bhang(ing)?\s+myself\b",
    r"\bdon'?t\s+want\s+to\s+live\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bbetter\s+off\s+dead\b",
]

_ALL_CRISIS_COMPILED = [
    re.compile(p, re.IGNORECASE) for p in (*_VI_CRISIS_REGEXES, *_EN_CRISIS_REGEXES)
]


def _strip_accents(text: str) -> str:
    """Normalize text and strip combining diacritics for fallback matching."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_crisis_message(text: str | None) -> bool:
    """True when the message contains indications of self-harm or suicidal ideation."""
    if not text or not isinstance(text, str):
        return False
    clean = text.strip()
    if not clean:
        return False

    # Check direct patterns
    for pattern in _ALL_CRISIS_COMPILED:
        if pattern.search(clean):
            return True

    # Check normalized accent-stripped version
    stripped = _strip_accents(clean)
    for pattern in _ALL_CRISIS_COMPILED:
        if pattern.search(stripped):
            return True

    return False


def build_crisis_reply(lang: str = "vi") -> str:
    """Return a supportive, empathetic safety reply with official Vietnamese crisis hotlines."""
    if lang.startswith("en"):
        return (
            "I'm really concerned about you and want you to be safe. "
            "You don't have to carry this alone. Please pause and reach out immediately "
            "to someone you trust or contact free crisis support in Vietnam:\n\n"
            "- Vietnam National Child Protection Hotline: 111 (toll-free 24/7)\n"
            "- Ngay Mai Mental Health Crisis Helpline: 096 306 1414\n"
            "- Emergency Medical Services: 115\n\n"
            "There are people who care and want to help you through this. Please reach out to them right now."
        )

    return (
        "Mình rất lo lắng cho bạn và muốn bạn được an toàn. "
        "Bạn không phải trải qua những cảm xúc này một mình. "
        "Hãy dừng lại một chút và liên hệ ngay với người thân hoặc các tổng đài hỗ trợ tâm lý hoàn toàn miễn phí:\n\n"
        "- Tổng đài Quốc gia Bảo vệ Trẻ em: 111 (miễn phí 24/7)\n"
        "- Đường dây nóng hỗ trợ tâm lý Ngày Mai: 096 306 1414\n"
        "- Cấp cứu y tế khẩn cấp: 115\n\n"
        "Luôn có những người sẵn sàng lắng nghe và đồng hành cùng bạn. Bạn rất quý giá, hãy giữ an toàn cho bản thân nhé."
    )


def redact_crisis_content(text: str) -> str:
    """Replace sensitive crisis text with a neutral placeholder so it is not stored in plain chat."""
    if is_crisis_message(text):
        return SAFE_REDACTION_MESSAGE
    return text
