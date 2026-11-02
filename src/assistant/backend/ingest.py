"""Deprecated: moved to app.ingest (ADR 003). Re-exported so old imports keep working."""

from app.ingest import MAX_UPLOAD_BYTES, InvalidPdf, extract_pages, looks_scanned

__all__ = ["MAX_UPLOAD_BYTES", "InvalidPdf", "extract_pages", "looks_scanned"]
