"""Plain text pasted from a course page, cut into PAGE_CHARS pieces."""

from app.ingest.base import DocumentFormat, InvalidDocument, split_text
from app.ingest.pdf import PdfFormat
from app.ingest.word import DocxFormat


class TextFormat(DocumentFormat):
    media_type = "text/plain"
    extensions = (".txt",)
    magic = b""

    def sniff(self, data: bytes) -> bool:
        # A PDF, DOCX or other binary renamed to .txt is refused, not read as garbage.
        return not data.startswith((PdfFormat.magic, DocxFormat.magic)) and (
            b"\x00" not in data[:1024]
        )

    def read(self, data: bytes) -> list[str]:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidDocument("not UTF-8") from exc
        lines = (" ".join(line.split()) for line in text.splitlines())
        pages = split_text("\n".join(line for line in lines if line))
        if not pages:
            raise InvalidDocument("no text")
        return pages
