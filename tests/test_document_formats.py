"""Document formats behind ingest (#49), without HTTP or a database."""

from io import BytesIO
from zipfile import ZipFile

import docx
import pytest
from docx.oxml import OxmlElement
from PIL import Image

from app.ingest import (
    PAGE_CHARS,
    DocxFormat,
    InvalidDocument,
    PptxFormat,
    TextFormat,
    UnsupportedType,
    as_pdf,
    detect_media_type,
    extract_pages,
)
from app.ingest import base as base_module
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
    monkeypatch.setattr(base_module, "MAX_UNZIPPED_BYTES", 1000)
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


def pptx(*slides: str, order: tuple[int, ...] | None = None, prolog: str = "") -> bytes:
    """A minimal deck; slide files are numbered 1..n, ``order`` is how the deck shows them."""
    order = order or tuple(range(1, len(slides) + 1))
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as package:
        ids = "".join(f'<p:sldId id="{255 + n}" r:id="rId{n}"/>' for n in order)
        package.writestr(
            "ppt/presentation.xml",
            f'<p:presentation xmlns:p="{p}" xmlns:r="{r}"><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>',
        )
        rels = "".join(
            f'<Relationship Id="rId{n}" Target="slides/slide{n}.xml"/>'
            for n in range(1, len(slides) + 1)
        )
        package.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>",
        )
        for n, text in enumerate(slides, 1):
            paragraphs = "".join(
                f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in text.split("\n")
            )
            package.writestr(
                f"ppt/slides/slide{n}.xml",
                f'{prolog}<p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree><p:sp><p:txBody>'
                f"{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
            )
    return buffer.getvalue()


def test_pptx_is_one_page_per_slide_in_presentation_order():
    deck = pptx("Use cases\nInclude vs extend", "Problem framing", order=(2, 1))
    assert detect_media_type("week2.pptx", deck) == PptxFormat.media_type
    assert extract_pages(deck, PptxFormat.media_type) == [
        "Problem framing",
        "Use cases\nInclude vs extend",
    ]
    assert as_pdf(deck, PptxFormat.media_type) is None  # the text is the slide


def test_pptx_never_expands_entities_and_refuses_non_decks():
    entity = "<!DOCTYPE s [<!ENTITY e 'boom'>]>"
    deck = pptx("&e;", prolog=entity)
    assert "boom" not in "".join(PptxFormat().read(deck))
    with pytest.raises(InvalidDocument):
        PptxFormat().read(deck.replace(b"ppt/slides/slide1.xml", b"ppt/slides/slideX.xml"))
    with pytest.raises(UnsupportedType):
        PptxFormat().read(saved(docx.Document()))


def test_photo_is_one_empty_page_that_vision_reads_as_pdf():
    photo = BytesIO()
    Image.new("RGB", (40, 30), "white").save(photo, "PNG")
    data = photo.getvalue()
    assert detect_media_type("board.PNG", data) == "image/png"
    assert extract_pages(data, "image/png") == [""]
    assert as_pdf(data, "image/png").startswith(b"%PDF")
    with pytest.raises(InvalidDocument):
        extract_pages(data[:20], "image/png")
    with pytest.raises(UnsupportedType):
        detect_media_type("board.jpg", data)  # a PNG renamed to .jpg
