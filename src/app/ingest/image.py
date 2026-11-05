"""Photos (JPEG, PNG) of notes, whiteboards or exam papers: one page, read visually (#114).

A photo has no text layer, so its page text is empty and the vision pass, which
reads PDFs, gets the photo wrapped as a one-page PDF.
"""

import warnings
from io import BytesIO

from PIL import Image

from app.ingest.base import DocumentFormat, InvalidDocument


class _ImageFormat(DocumentFormat):
    def read(self, data: bytes) -> list[str]:
        self._open(data)
        return [""]

    def as_pdf(self, data: bytes) -> bytes:
        output = BytesIO()
        self._open(data).convert("RGB").save(output, "PDF")
        return output.getvalue()

    @staticmethod
    def _open(data: bytes) -> Image.Image:
        # A decompression bomb is refused, not just warned about.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                image = Image.open(BytesIO(data))
                image.load()
            except (OSError, ValueError, Image.DecompressionBombError,
                    Image.DecompressionBombWarning) as exc:
                raise InvalidDocument(type(exc).__name__) from exc
        return image


class JpegFormat(_ImageFormat):
    media_type = "image/jpeg"
    extensions = (".jpg", ".jpeg")
    magic = b"\xff\xd8\xff"


class PngFormat(_ImageFormat):
    media_type = "image/png"
    extensions = (".png",)
    magic = b"\x89PNG\r\n\x1a\n"
