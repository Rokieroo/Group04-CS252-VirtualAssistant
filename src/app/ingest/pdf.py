from io import BytesIO

from pypdf import PdfReader

MAX_PDF_BYTES = 20 * 1024 * 1024


class PDFError(ValueError):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


def extract_pdf(data: bytes, file_name: str) -> tuple[list[str], list[str]]:
    if len(data) > MAX_PDF_BYTES:
        raise PDFError(413, "file_too_large")
    if not file_name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise PDFError(415, "not_pdf")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        if not pages:
            raise ValueError("Empty PDF")
    except Exception as exc:
        raise PDFError(400, "invalid_pdf") from exc
    warnings = ["scanned_pdf"] if sum(not value for value in pages) / len(pages) > 0.8 else []
    return pages, warnings
