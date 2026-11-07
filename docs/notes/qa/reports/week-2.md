# Weekly QA Report — Week 2

This report summarizes testing, quality assurance, benchmark validation, and core loop integration results for **Week 2** of the Study Companion project.

- **Reporting Period:** Week 2 (2026-10-25 – 2026-10-31)
- **Lead / QA Engineer:** Le Hong Dang (QA/QC)
- **Primary Milestone:** Core Loop Foundation (Syllabus Ingest, Roadmap Topological Generation & Resource Search Prototype)
- **Specification Version Reference:** Spec 3.0 / 3.1 (Sections 13.1, 14, 15)

---

## 1. Executive Summary

- **Status:** **PASSED** — Core loop foundations, DAG scheduling invariants, and API contracts verified.
- The automated test suite expanded significantly from 168 tests (Week 1) to **420+ automated tests**, achieving a **100% pass rate** in offline CI execution.
- Designed and verified topological sort invariants: 0 directed cycles detected across generated course roadmaps; Kahn's algorithm and Tarjan SCC cycle fallback verified.
- Initial latency benchmarking on the CSC10014 syllabus indicated deterministic preview extraction takes $\approx 14.4\text{ ms}$, roadmap linking takes $< 1\text{ ms}$, and EDF schedule allocation takes $\approx 13.8\text{ ms}$ (Total local processing $< 30\text{ ms}$, well under the 30-second target in Spec Section 14).

---

## 2. Test Execution & Coverage Summary

| Test Category | Suite / Command | Total Tests | Passed | Failed | Execution Time | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **Backend Unit Tests** | `python dev.py qa test` | 385 | 385 | 0 | 42.1s | Unit tests covering auth, syllabus parsing, roadmap topo sort, planner, safe fetcher |
| **Integration Tests** | `pytest tests/test_integration.py` | 12 | 12 | 0 | 7.2s | Cross-module tests: multi-page ingest, BM25 retrieval, IDOR protection |
| **Roadmap & Scheduling Tests** | `pytest tests/test_roadmap.py tests/test_scheduler.py` | 32 | 32 | 0 | 3.5s | Topo sort, DAG cycle prevention, EDF scheduling, daily budget boundaries |
| **Total Automated Tests** | `pytest tests/` | **429** | **429** | **0** | **~55s** | Fully offline with `LLM_PROVIDER=fake`, zero live API dependencies |
| **Benchmark Validation** | `python dev.py ai benchmark validate` | 20 | 20 | 0 | 0.8s | Verified 20 Q&A benchmark schemas (UC-10, UC-12, UC-13, UC-14) |
| **Lint & Secret Scan** | `ruff check .` · `dev db scan-secrets` | — | Pass | 0 | 1.2s | 0 lint errors, 0 detected credentials/secrets |

---

## 3. Core Loop Verification (UC-01 to UC-04)

### A. Syllabus Ingest & Deterministic Extraction (UC-01, UC-02)

- Evaluated multi-page PDF/DOCX/Text ingestion. Deterministic parser extracts course code, term dates, outcomes (CLO), weekly breakdown, and assessments with exact `source_page` grounding.
- Negative boundary tests confirmed:
  - Empty or non-syllabus text triggers HTTP 422 (`not_a_syllabus`).
  - Corrupted files trigger HTTP 400.
  - Non-supported media types (e.g. `.gif`) trigger HTTP 415.

### B. Roadmap Generation & Cycle Invariants (UC-03)

- Validated roadmap generation via `link(derive_nodes(...))` producing a Directed Acyclic Graph (DAG).
- Hard constraint verified: Assessment milestone nodes cover preceding topic nodes and cannot have due dates preceding their prerequisites.
- Synthetic cycle injection tests confirmed that introducing circular prerequisite dependencies is rejected or resolved deterministically without hanging the backend.

### C. Earliest-Deadline-First Scheduling (UC-04)

- Verified schedule allocation algorithm:
  - Splits tasks cleanly around user-defined busy blocks (`test_plan_splits_tasks_around_busy_time_and_preserves_every_minute`).
  - Preserves every minute of allocated task duration without loss.
  - Accurately reports `insufficient_capacity` or `deadline_passed` in the `unscheduled` payload when user study windows are insufficient.

---

## 4. Spec 15 Metric Tracking (Week 2 Baseline)

| Spec 15 Metric | Baseline / Target | Week 2 Measured Result | Status | Notes |
| --- | --- | --- | :---: | --- |
| **Syllabus to Roadmap Latency** | Target $\le 10$ minutes | $< 0.05$ seconds (local compute) | 🟢 Met | Measured on CSC10014 benchmark syllabus offline |
| **Syllabus Extraction F1** | Target $\ge 90\%$ | 92.4% (deterministic parser) | 🟢 Met | Validated against gold-standard extraction schemas |
| **Roadmap Directed Cycles** | Target: 0 cycles | 0 cycles | 🟢 Met | Verified by Kahn topological sort unit tests |
| **Cross-User Access Isolation** | 0 IDOR leaks | 0 leaks (HTTP 404 on cross access) | 🟢 Met | Verified by `test_auth_cross_user_course_access_denied_404` |
| **Link Integrity Baseline** | Target $\le 1\%$ dead links | N/A (Prototype phase) | 🟡 In Progress | Live search pipeline under development in Week 3 |

---

## 5. Bug Log (Week 2)

| # | Severity | Description | Assigned Role | Related Reference | Resolution Status |
| --- | --- | --- | --- | --- | --- |
| 1 | Major | Replan endpoint permitted repeated unconstrained proposal requests, causing potential denial-of-service / duplicate proposals. | DB & Security | Issue #65 | Resolved: Rate-limited to 1 proposal per day per user (HTTP 429) |
| 2 | Major | Ingesting multi-page syllabus PDFs with corrupted cross-reference tables caused unhandled parser crashes. | DB & Security | Issue #49 | Resolved: Added defensive error handling returning HTTP 400 |
| 3 | Minor | Local midnight reset in user timezone was calculating start of day using server UTC offset rather than user profile timezone. | AI / Backend | Issue #52 | Resolved: Converted `now` to `ZoneInfo(user.timezone)` |

---

## 6. Limitations & Action Items for Week 3

1. **Staging Resource Search Testing**: Live resource curation (UC-05) requires search provider API keys and external network access, which cannot run in offline CI. Mocked test pipelines with `FakeSearch` and `SafeFetcher` are required for CI stability.
2. **Multi-format Benchmark Expansion**: Prepare multi-subject benchmark syllabi (CS, SE, Networks, Cloud) to validate parser generality in Week 3.
