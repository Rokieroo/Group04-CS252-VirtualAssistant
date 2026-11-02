"""Ingest: reads uploaded files into per-page text (spec 6.1)."""

from app.ingest.pdf import MAX_UPLOAD_BYTES, InvalidPdf, extract_pages, looks_scanned

__all__ = ["MAX_UPLOAD_BYTES", "InvalidPdf", "extract_pages", "looks_scanned"]
