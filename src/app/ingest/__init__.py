"""Ingest: reads uploaded PDF, DOCX or plain text into per-page text (spec 6.1, 9.2)."""

from app.ingest.base import (
    MAX_UPLOAD_BYTES,
    PAGE_CHARS,
    DocumentFormat,
    InvalidDocument,
    UnsupportedType,
)
from app.ingest.pdf import InvalidPdf, PdfFormat, looks_scanned
from app.ingest.text import TextFormat
from app.ingest.word import DocxFormat

FORMATS: tuple[DocumentFormat, ...] = (PdfFormat(), DocxFormat(), TextFormat())
_BY_MEDIA_TYPE = {document.media_type: document for document in FORMATS}
PDF = PdfFormat.media_type

__all__ = [
    "FORMATS",
    "MAX_UPLOAD_BYTES",
    "PAGE_CHARS",
    "PDF",
    "DocumentFormat",
    "DocxFormat",
    "InvalidDocument",
    "InvalidPdf",
    "PdfFormat",
    "TextFormat",
    "UnsupportedType",
    "detect_media_type",
    "extract_pages",
    "looks_scanned",
]


def detect_media_type(file_name: str, data: bytes) -> str:
    """The media type whose extension and leading bytes both match; never trusts the client."""
    for document in FORMATS:
        if document.matches(file_name, data):
            return document.media_type
    raise UnsupportedType(file_name)


def extract_pages(data: bytes, media_type: str = PDF) -> list[str]:
    """One string per page. PDF is the default so Phase 1 callers keep working."""
    document = _BY_MEDIA_TYPE.get(media_type)
    if document is None:
        raise UnsupportedType(media_type)
    return document.read(data)
