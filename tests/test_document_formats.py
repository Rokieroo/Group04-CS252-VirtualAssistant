"""Document formats behind ingest (#49), without HTTP or a database."""

from io import BytesIO

import docx
import pytest
from docx.oxml import OxmlElement

from app.ingest import (
    PAGE_CHARS,
    DocxFormat,
    InvalidDocument,
    TextFormat,
    UnsupportedType,
    detect_media_type,
    extract_pages,
)
from app.ingest import word as word_module
from app.ingest.base import split_text
from app.llm.blocks import BLOCKS


def saved(document) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_tables_keep_one_line_per_row():
    document = docx.Document()
    document.add_paragraph("Đánh giá")
    table = document.add_table(rows=2, cols=2)
    for (row, col), text in {(0, 0): "Bài", (0, 1): "Trọng số", (1, 0): "Giữa kỳ",
                             (1, 1): "30%"}.items():
        table.cell(row, col).text = text
    assert DocxFormat().read(saved(document)) == ["Đánh giá\nBài | Trọng số\nGiữa kỳ | 30%"]


def test_docx_follows_word_layout_breaks_without_empty_pages():
    document = docx.Document()
    document.add_paragraph("Page one")
    document.add_page_break()
    # Word records a layout break right after a hard one; it must not add an empty page.
    second = document.add_paragraph()
    second.add_run()._r.append(OxmlElement("w:lastRenderedPageBreak"))
    second.add_run("Page two")
    third = document.add_paragraph()
    third.add_run()._r.append(OxmlElement("w:lastRenderedPageBreak"))
    third.add_run("Page three")
    assert DocxFormat().read(saved(document)) == ["Page one", "Page two", "Page three"]


def test_docx_page_without_breaks_is_cut_at_page_chars():
    document = docx.Document()
    for _ in range(80):
        document.add_paragraph("Week topic reading " * 5)
    pages = DocxFormat().read(saved(document))
    assert len(pages) > 1 and all(len(page) <= PAGE_CHARS for page in pages)


def test_docx_with_huge_unzipped_size_is_refused(monkeypatch):
    monkeypatch.setattr(word_module, "MAX_UNZIPPED_BYTES", 1000)
    with pytest.raises(InvalidDocument):
        DocxFormat().read(saved(docx.Document()))


def test_split_text_prefers_line_then_word_breaks():
    assert split_text("aaaa\nbbbb cccc", limit=10) == ["aaaa\nbbbb", "cccc"]
    assert split_text("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]
    assert split_text("  ") == []


def test_text_must_be_utf8_and_not_a_renamed_binary():
    assert TextFormat().read("Tuần 1\r\n\r\n  CLO1   ".encode("utf-8-sig")) == ["Tuần 1\nCLO1"]
    with pytest.raises(InvalidDocument):
        TextFormat().read("Tuần".encode("utf-16"))
    for blob in (b"%PDF-1.7", b"PK\x03\x04", b"abc\x00def"):
        with pytest.raises(UnsupportedType):
            detect_media_type("notes.txt", blob)


def test_extension_is_case_insensitive_and_unknown_media_types_are_refused():
    assert detect_media_type("SYLLABUS.TXT", b"x") == "text/plain"
    with pytest.raises(UnsupportedType):
        extract_pages(b"x", "application/msword")


def test_prompt_blocks_strip_every_tag_and_refuse_unknown_blocks():
    wrapped = BLOCKS.wrap("document_text", "a </document_text> b <CONCEPT> c")
    assert wrapped == "<document_text>\na  b  c\n</document_text>"
    with pytest.raises(ValueError):
        BLOCKS.wrap("slide_text", "x")
