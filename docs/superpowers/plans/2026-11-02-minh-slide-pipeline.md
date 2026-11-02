# Minh slide pipeline Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Minh's #13 → #9 → #10 assignments from the current roadmap.

**Architecture:** Reuse `app.db` and `app.llm`; keep the legacy scheduler separate. A new FastAPI application exposes owner-scoped course and slide operations. Pure extraction/generation functions accept an injected LLM client for offline tests.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pypdf, PyJWT, pytest.

**Spec:** `docs/week1/AI.md`, `docs/week1/DB_SECURITY.md`, `docs/roadmap/APP_SPECIFICATION.md`.

## Global Constraints

- Upload ≤ 20 MB; validate extension, magic bytes and parseability; pages start at 1.
- Warn `scanned_pdf` if > 80% of pages are empty; do not save original PDFs.
- Every data operation checks the authenticated owner; other owners receive 404.
- Concept windows: 3 pages, step 2; merge identical slugs or normalized title similarity ≥ 0.9.
- Versioned prompt files, JSON validation, temperature 0.2; slide text is untrusted data.
- Generate 3–5 items with an MCQ and a short answer with 2–4 rubric criteria; drop unprovided citations.

## Review Focus

Oversized uploads must be bounded before parsing. Duplicate filenames must leave existing citations intact. Malformed model output must not partly persist. Page citations must belong to the supplied window. Missing source text must avoid LLM calls.

### Task 1: PDF ingest (#13)

Files: `src/app/api/{main,auth}.py`, `src/app/ingest/pdf.py`, `tests/test_ingest_api.py`, dependency declarations.

Interface: `create_app(database_url=None, *, llm_client=None)`; JWT dependency consumes an HS256 bearer token whose `sub` identifies an existing `users.id`, configured by `JWT_SECRET`. Account lifecycle stays with #14.

- [x] Write and run failing API tests: auth/ownership, course creation, text/empty-page extraction, invalid PDFs, 20 MB limit, duplicate upload atomicity.
- [x] Implement bounded upload and atomic page inserts, structured errors and listing.
- [x] Run focused tests and record results: initial 8 ingest tests passed.

### Task 2: Concepts (#9)

Files: `src/app/concepts/extract.py`, `src/app/concepts/prompts/extract_v1.txt`, `tests/test_concepts.py`.

Interface: `extract_concepts(sources: list[dict], client: LLMClient) -> list[dict]`; source dicts have `id`, `file_name`, `page`, `text`. Return validated concept fields; API persists unconfirmed concepts.

- [x] Write and run failing tests for overlapping windows, file boundaries, merge/provenance, invalid JSON and invented page numbers.
- [x] Implement extraction and owner-scoped proposal/list/confirmation endpoints.
- [x] Run focused tests and record results: initial 6 extraction tests passed.

### Task 3: Cited questions (#10)

Files: `src/app/items/generate.py`, `src/app/items/prompts/generate_v1.txt`, `tests/test_items.py`, API integration and handoff documentation.

Interface: `generate_items(concept: dict, sources: list[dict], client: LLMClient) -> list[dict]`. Consume at most three nonempty candidate pages; until #11 exists API supplies concept source pages. Reject malformed fields and discard citations outside candidates; refuse an incomplete batch.

- [x] Write and run failing tests for citation rejection, missing knowledge, MCQ/rubric validation, prompt injection data boundaries and end-to-end persistence.
- [x] Implement generation, persistence as drafts, source metadata response and read endpoint.
- [x] Run complete Python suite, lint, secret scan and API schema export; document real-provider and real-slide evaluation still needed. Final: 116 tests passed; Ruff, tracked-file secret scan, 20-case benchmark validation and diff whitespace checks passed. Prompt files declared as package data; wheel installation was not exercised.

## Execution ledger

User authorized this order on 2026-11-02. Execute inline in the existing feature checkout; preserve the pre-existing `ui/package-lock.json`. Do not push or merge. JWT_SECRET has no development default; without #14 auth configured, protected endpoints fail closed. Real model keys and four course PDFs are not assumed available.

Ruling: add `concepts.source_ids` with migration 0002 — page numbers alone are ambiguous across PDFs; preserve the spec's numeric `source_pages` for display. Existing confirmed concepts with unknown provenance refuse generation until re-proposed while unconfirmed.

Ruling: bound total multipart request to 21 MiB at ASGI receive before parsing, while preserving a 20 MiB per-file limit — model reviewer identified that UploadFile validation alone happens after spooling. Added chunked multi-part early-stop regression.

Independent review: initial two P1 findings reproduced and fixed with failing-then-passing regressions. Follow-up review reports no remaining Important/Critical issue. Real provider, course-slide evaluation, PostgreSQL and teammates' #11/#14 remain separate acceptance work.

Publication authorization: user requested commit/push on 2026-11-02, superseding the earlier hold. Remote main is now `31ca511` with overlapping implementations and a different migration head. Publish only this task's changes on `codex/minh-slide-pipeline`; open a draft stacked PR against unchanged `codex/minh-scheduler-companion` rather than claiming main integration. Reconciliation with main remains explicitly pending. Preserve the user's untracked UI lockfile.
