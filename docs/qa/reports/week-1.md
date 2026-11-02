# Weekly QA Report — Week 1

This report summarizes the testing and quality assurance results for Week 1.  
- **Initial Date:** 2026-10-24  
- **Last Updated:** 2026-10-31 (Integrated Issue #16 Integration Tests)  
- **Lead / QA Engineer:** Le Hong Dang (QA/QC)

---

## 1. Executive Summary
- **Status:** **PASSED** across test infrastructure, continuous integration, and cross-module integration.
- The project achieved a 100% pass rate on all automated suites: **168/168 tests passed** in offline test execution, CI verification passed, and benchmark dataset format validated.
- Added **12 independent integration test cases** (#16) verifying PDF Ingestion, BM25 Retrieval, Auth & Access Control isolation (IDOR protection), and End-to-End user journeys.

---

## 2. Test Execution Results

| Test Category | Suite / Command | Total Tests | Passed | Failed | Notes |
|---|---|---:|---:|---:|---|
| **Backend Unit Tests** | `python dev.py qa test` | 156 | 156 | 0 | Pytest across auth, ingest, llm, scheduler, concepts, and retrieval |
| **Integration Tests (#16)** | `pytest tests/test_integration.py` | 12 | 12 | 0 | Independent integration across Ingest, BM25, Auth isolation, and E2E |
| **Total Automated Tests** | `python dev.py devops ci` | **168** | **168** | **0** | Runs fully offline without external network or live LLM credentials |
| **Benchmark Evaluation** | `python dev.py ai benchmark stats` | 20 | 20 | 0 | Validated schemas: normal=10, missing_knowledge=4, privacy=3, safety=3 |
| **Safeguard / Red-Team** | Red-team benchmark cases | 10 | 10 | 0 | Pre-configured guardrail evaluation cases |

---

## 3. Integration Test Breakdown (Issue #16)

### A. PDF Ingestion (4 Tests)
1. `test_ingest_three_page_pdf_success`: Uploading a valid 3-page PDF extracts exactly 3 numbered records (`pages=1, 2, 3`) in the `sources` table.
2. `test_ingest_corrupted_pdf_rejected_400`: Corrupted or malformed PDF payloads are rejected with HTTP `400 Bad Request`.
3. `test_ingest_unsupported_file_type_rejected_415`: Non-PDF files (e.g. `.txt`) are rejected with HTTP `415 Unsupported Media Type`.
4. `test_ingest_oversized_file_rejected_413`: Payloads exceeding the 20MB limit trigger the upload size middleware and return HTTP `413 Payload Too Large`.

### B. BM25 Retrieval (3 Tests)
5. `test_retrieval_keyword_beta_ranks_page_2_first`: BM25 query for `"beta"` ranks Page 2 as the top hit among course slides.
6. `test_retrieval_unknown_keyword_returns_empty`: Querying out-of-document terms (`"zzzz"`) scores below threshold and returns an empty list `[]`.
7. `test_retrieval_empty_course_sources_returns_empty`: Querying an empty course with zero ingested sources safely returns `[]` without exceptions.

### C. Authentication & Access Control (4 Tests)
8. `test_auth_login_wrong_password_rejected_401`: Login attempts with invalid credentials return HTTP `401 Unauthorized`.
9. `test_auth_expired_token_rejected_401`: Accessing protected endpoints with an expired session token returns HTTP `401 Unauthorized`.
10. `test_auth_cross_user_course_access_denied_404`: User A attempting to inspect or list resources from User B's course is rejected with HTTP `404 Not Found` (preventing IDOR and resource enumeration).
11. `test_auth_missing_header_rejected_401`: Requests omitting the `Authorization: Bearer <token>` header return HTTP `401 Unauthorized`.

### D. End-to-End Integration Flow (1 Test)
12. `test_e2e_register_create_course_upload_and_retrieve`: Verifies the full user journey:
    $$\text{Register} \longrightarrow \text{Create Course} \longrightarrow \text{Upload 3-Page PDF} \longrightarrow \text{BM25 Retrieve} \longrightarrow \text{Page 1 Match}$$

---

## 4. Bug Log

| # | Severity | Description | Assigned Role | Related Reference | Resolution Status |
|---|---|---|---|---|---|
| 1 | Major | Merging `main` into the LLM branch caused overlapping `if` blocks in `src/devcli/db.py`, breaking Ruff lint, pytest, and secret scanner. | AI Implementation | PR #22 | Resolved (commit `5b6787f`) |
| 2 | Minor | Benchmark case B002 cited `Week 0 - Orientation.pdf#53` from printed slide numbering instead of the canonical PDF page index (50). | QA/QC | Issue #15 | Resolved (aligned to PDF index) |

---

## 5. Limitations & Next Steps

| # | Current Limitation | Improvement Plan |
|---|---|---|
| 1 | Benchmark currently validates formatting and static citations only. | Implement an automated pipeline runner script to score live LLM responses once question generation (#10) merges. |
| 2 | Frontend UI unit tests (Vitest) are not yet integrated into CI. | Propose adding an `npm test` step in the GitHub Actions workflow during Week 2. |
| 3 | Discrepancies between printed slide page numbers and PDF indices. | Enforce physical PDF index convention across all test and benchmark citations (TEST_PLAN Section 3). |
