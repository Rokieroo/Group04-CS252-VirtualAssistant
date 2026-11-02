"""What every document format shares: errors, the upload limit and page splitting.

Document text is data only, never a prompt (spec 12.3).
"""

from abc import ABC, abstractmethod

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
PAGE_CHARS = 3000  # a "page" for formats without real pages (spec 9.2)


class InvalidDocument(ValueError):
    """The file is of a supported type but cannot be read. `code` is the API error."""

    code = "invalid_file"


class UnsupportedType(ValueError):
    """The file name and leading bytes do not match any format we read."""


class DocumentFormat(ABC):
    """One readable file type: how to recognise it and how to split it into pages."""

    media_type: str
    extensions: tuple[str, ...]
    magic: bytes

    def matches(self, file_name: str, data: bytes) -> bool:
        """Name and content must agree; an empty file is left for read() to reject."""
        return file_name.lower().endswith(self.extensions) and (
            not data or self.sniff(data)
        )

    def sniff(self, data: bytes) -> bool:
        return data.startswith(self.magic)

    @abstractmethod
    def read(self, data: bytes) -> list[str]:
        """One string per page, in order. Raises InvalidDocument or UnsupportedType."""


def split_text(text: str, limit: int = PAGE_CHARS) -> list[str]:
    """Cut text into pieces of at most `limit` characters, at a line or word break if any."""
    pieces = []
    text = text.strip()
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit + 1), text.rfind(" ", 0, limit + 1))
        if cut <= 0:
            cut = limit
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        pieces.append(text)
    return pieces
