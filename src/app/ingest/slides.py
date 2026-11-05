"""PPTX: one page per slide, in the order the deck shows them (#114).

Slide files keep their number when a slide is moved, so the order comes from
``ppt/presentation.xml``, not from file names. Each text paragraph becomes a line;
speaker notes are not part of the slide and are left out.
"""

import posixpath
import zlib
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from lxml import etree

from app.ingest.base import DocumentFormat, InvalidDocument, check_package

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
# Untrusted XML: no entity expansion, no network, no huge trees.
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


class PptxFormat(DocumentFormat):
    media_type = (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    extensions = (".pptx",)
    magic = b"PK\x03\x04"

    def read(self, data: bytes) -> list[str]:
        check_package(data, "ppt/presentation.xml")
        try:
            with ZipFile(BytesIO(data)) as package:
                pages = [_slide_text(package.read(name)) for name in _slide_names(package)]
        except (KeyError, BadZipFile, zlib.error, etree.XMLSyntaxError) as exc:
            raise InvalidDocument(type(exc).__name__) from exc
        if not pages:
            raise InvalidDocument("no slides")
        return pages


def _xml(package: ZipFile, name: str):
    return etree.fromstring(package.read(name), _PARSER)


def _slide_names(package: ZipFile) -> list[str]:
    """Part names of the slides, in presentation order."""
    targets = {
        rel.get("Id"): rel.get("Target")
        for rel in _xml(package, "ppt/_rels/presentation.xml.rels").iterfind(
            "rel:Relationship", _NS
        )
    }
    ids = _xml(package, "ppt/presentation.xml").iterfind("p:sldIdLst/p:sldId", _NS)
    return [
        posixpath.normpath(posixpath.join("ppt", targets[slide.get(f"{{{_NS['r']}}}id")]))
        for slide in ids
    ]


def _slide_text(xml: bytes) -> str:
    root = etree.fromstring(xml, _PARSER)
    lines = (
        "".join(run.text or "" for run in paragraph.iterfind(".//a:t", _NS)).strip()
        for paragraph in root.iterfind(".//a:p", _NS)
    )
    return "\n".join(line for line in lines if line)
