"""PDF: one page of extracted text per PDF page (UC-01)."""

from io import BytesIO

from pypdf import PdfReader

from app.ingest.base import DocumentFormat, InvalidDocument

SCANNED_RATIO = 0.8


class InvalidPdf(InvalidDocument):
    code = "invalid_pdf"


class PdfFormat(DocumentFormat):
    media_type = "application/pdf"
    extensions = (".pdf",)
    magic = b"%PDF"

    def read(self, data: bytes) -> list[str]:
        """Normalize whitespace within lines, preserving syllabus section boundaries."""
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise InvalidPdf("encrypted")
            pages = [
                "\n".join(
                    " ".join(line.split())
                    for line in (page.extract_text() or "").splitlines()
                    if line.strip()
                )
                for page in reader.pages
            ]
        except InvalidPdf:
            raise
        except Exception as exc:  # pypdf raises many types for malformed files
            raise InvalidPdf(type(exc).__name__) from exc
        if not pages:
            raise InvalidPdf("no pages")
        return pages

    def as_pdf(self, data: bytes) -> bytes:
        return data


def looks_scanned(pages: list[str]) -> bool:
    return sum(not text for text in pages) > SCANNED_RATIO * len(pages)
