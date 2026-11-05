"""DOCX: split at Word's page breaks, then into PAGE_CHARS pieces; tables keep their rows.

Named word.py so it never shadows the python-docx package (`import docx`).
"""

from io import BytesIO

import docx
from docx.oxml.ns import qn

from app.ingest.base import DocumentFormat, InvalidDocument, check_package, split_text

_P, _TABLE, _ROW, _CELL = qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc")
_TEXT, _TAB, _BREAK, _RETURN = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
_RENDERED_BREAK, _BREAK_BEFORE = qn("w:lastRenderedPageBreak"), qn("w:pageBreakBefore")
_TYPE = qn("w:type")


class DocxFormat(DocumentFormat):
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    extensions = (".docx",)
    magic = b"PK\x03\x04"

    def read(self, data: bytes) -> list[str]:
        check_package(data, "word/document.xml")
        try:
            body = docx.Document(BytesIO(data)).element.body
        except Exception as exc:  # python-docx raises many types for malformed parts
            raise InvalidDocument(type(exc).__name__) from exc
        pages = [piece for page in _PageWriter().write(body) for piece in split_text(page)]
        if not pages:
            raise InvalidDocument("no text")
        return pages


class _PageWriter:
    """Walks a document body in order and starts a new page at every page break.

    Hard breaks, "page break before" and the breaks Word recorded when it last laid
    the file out all count, so page numbers match what the student sees in Word.
    """

    def __init__(self):
        self.pages: list[list[str]] = [[]]
        self.line: list[str] = []

    def write(self, body) -> list[str]:
        for block in body.iterchildren():
            if block.tag == _P:
                self._paragraph(block)
            elif block.tag == _TABLE:
                self._table(block)
        self._end_line()
        return ["\n".join(lines) for lines in self.pages if lines]

    def _paragraph(self, paragraph) -> None:
        if paragraph.find(f"./{qn('w:pPr')}/{_BREAK_BEFORE}") is not None:
            self._new_page()
        for node in paragraph.iter():
            if node.tag == _TEXT:
                self.line.append(node.text or "")
            elif node.tag == _TAB:
                self.line.append(" ")
            elif node.tag == _RENDERED_BREAK or (
                node.tag == _BREAK and node.get(_TYPE) == "page"
            ):
                self._new_page()
            elif node.tag in (_BREAK, _RETURN):
                self._end_line()
        self._end_line()

    def _table(self, table) -> None:
        # One line per row, "cell | cell", so the row/column structure survives (spec 9.2).
        for row in table.iterchildren(_ROW):
            if row.find(f".//{_RENDERED_BREAK}") is not None:
                self._new_page()
            cells = [
                " ".join("".join(t.text or "" for t in p.iter(_TEXT)) for p in cell.iter(_P))
                for cell in row.iterchildren(_CELL)
            ]
            self.line.append(" | ".join(cells))
            self._end_line()

    def _end_line(self) -> None:
        text = " ".join("".join(self.line).split())
        if text:
            self.pages[-1].append(text)
        self.line = []

    def _new_page(self) -> None:
        self._end_line()
        # Word often records a rendered break right after a hard one; skip empty pages.
        if self.pages[-1]:
            self.pages.append([])
