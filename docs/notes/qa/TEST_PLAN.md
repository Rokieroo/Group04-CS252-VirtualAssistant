# Test Plan — Core Loop (Weeks 1–3)

This document specifies the testing scope, verification layers, acceptance criteria, benchmark datasets, and defect tracking procedures for the Study Companion application. It is aligned with Product Specification 3.0/3.1 (Section 13.1 Safeguards, Section 14 Non-Functional Requirements, and Section 15 Target Metrics).

---

## 1. Testing Scope (Core Loop: UC-01 to UC-07)

Phase 2 focuses on verifying the end-to-end **Core Loop**: Syllabus Ingestion $\longrightarrow$ Citation-grounded Preview $\longrightarrow$ DAG Roadmap Generation $\longrightarrow$ Capacity-aware Scheduling $\longrightarrow$ Verified Resource Retrieval $\longrightarrow$ Feedback & Rescheduling.

| Use Case | Feature | Capability / Method | Acceptance Criteria | Test Layer |
| --- | --- | --- | --- | --- |
| **UC-01** | Upload syllabus | Deterministic page-level text extraction (PDF / DOCX / TXT) | HTTP 201; exact page count; rejects corrupted payloads (400), unsupported MIME types (415), and oversized payloads (413). | Integration, E2E |
| **UC-02** | Review and confirm syllabus | Deterministic rules with LLM fallback and page citations | Returns preview containing course metadata, CLOs, weekly topics, and assessments with physical `source_page` citations. $F_1 \ge 90\%$. | Unit, Eval, E2E |
| **UC-03** | Generate roadmap from prerequisites | Topological sort DAG (Kahn's algorithm), cycle prevention | Zero directed cycles (0 cycles); topic nodes precede dependent milestone nodes; valid CLO bindings; generation latency $< 5\text{s}$. | Unit, Integration, E2E |
| **UC-04** | Schedule roadmap into calendar | Earliest-Deadline-First (EDF) within availability windows | Study sessions scheduled around user busy blocks without overlap; flags `overloaded_weeks` upon capacity shortfall; adheres to `max_daily_minutes`. | Unit, E2E |
| **UC-05** | Curate verified resources for nodes | Multi-provider search + SafeFetcher + LLM judge | Returns 3–5 resources per topic node with score $\ge 0.65$; 0 hallucinated links; 0 copyright-infringing/pirated domains; verbatim `evidence_quote`. | Unit, Eval, E2E |
| **UC-06** | Rate, save, and report resources | Deterministic feedback loop and rank adjustment | Persists helpful/unhelpful feedback; automatically surfaces reserve candidates when resources are reported dead or misaligned. | Unit, Integration, E2E |
| **UC-07** | Replan roadmap upon schedule shifts | Differential calculation and forward task rescheduling | Preserves 100% of completed sessions and tasks; reschedules pending workload only; rate-limited to 1 proposal per day. | Unit, Integration, E2E |

**Auxiliary Features (Phase 3 / Week 4+)**:

- **UC-10**: Curated practice items linked to verified sources.
- **UC-11**: Spaced repetition review sessions (FSRS).
- **UC-12**: Grounded Q&A with document page citations (BM25 + Dense vector retrieval).
- **UC-13**: Socratic hint ladder (progressive hints without revealing graded solutions).
- **UC-14**: Safe, age-appropriate companion interaction.
- **UC-18**: Interactive Obsidian-style Knowledge Graph canvas.

---

## 2. Test Verification Layers

```text
       ┌────────────────────────────────────────────────────────┐
       │             E2E Core Loop Integration Tests            │  tests/test_e2e_core_loop.py
       │     (Syllabus -> Roadmap -> Schedule -> Resources)     │  (Full user journey, offline)
       ├────────────────────────────────────────────────────────┤
       │         Benchmark Suites & Red-Team Safeguards         │  eval/ (20 Q&A, 10 Syllabi,
       │  (F1 extraction, Precision@5, Pirated URLs, Injections) │  150 Resources, 15 Injections)
       ├────────────────────────────────────────────────────────┤
       │       Component Integration Tests (FastAPI + DB)       │  tests/test_integration.py
       │  (PDF ingest, BM25 retrieval, Multi-tenant RBAC/IDOR)  │  tests/test_resources_api.py
       ├────────────────────────────────────────────────────────┤
       │                   Backend Unit Tests                   │  tests/test_*.py
       │     (Auth, Scheduler, Roadmap topo, SafeFetcher)       │  (630+ automated tests)
       └────────────────────────────────────────────────────────┘
```

| Layer | Tools | Execution Command | Pass Criteria |
| --- | --- | --- | --- |
| **Unit Tests** | Pytest | `python dev.py qa test` | 100% pass rate (633+ tests), completely offline without network or external API dependencies. |
| **Component Integration** | Pytest + Starlette TestClient | `pytest tests/test_integration.py tests/test_resources_api.py` | 100% pass rate; validates file ingestion, multi-tenant RBAC isolation, job queues, and search endpoints. |
| **E2E Core Loop** | Pytest (`test_e2e_core_loop.py`) | `pytest tests/test_e2e_core_loop.py` | 100% pass rate; verifies seamless execution across UC-01 to UC-07 using deterministic mock adapters. |
| **Benchmark Evaluation** | CLI Benchmark Validator | `python dev.py ai benchmark validate` | Schema and integrity validation for gold standards, resource URLs, and red-team suites. |
| **Red-Team & Safeguards** | Benchmark Stats Validator | `python dev.py ai benchmark stats` | 100% defense rate against 15 prompt injection vectors, 20 pirated URLs, and 10 synthetic PII leakages. |
| **Lint & Secret Scan** | Ruff & Secret Scanner | `ruff check .` · `python dev.py db scan-secrets` | 0 lint errors, 0 committed credentials or secrets. |
| **Continuous Integration** | GitHub Actions | Defined in `.github/workflows/ci.yml` | All pipeline jobs (Lint, Test, PostgreSQL Integration) pass cleanly on push and pull request. |

---

## 3. Benchmark Datasets & Ground Truth Conventions

1. **Syllabus Benchmark (`eval/syllabus/`)**:
   - 10 multi-subject syllabus samples (Computer Science, Software Engineering, AI, Networking, Cloud Computing) across `.txt`, `.docx`, and `.pdf` formats.
   - Corresponding `.gold.json` files define ground truth CLOs, weekly schedules, and assessments to compute parser precision, recall, and $F_1$ score.
2. **Resource Curation Benchmark (`eval/resources.jsonl`)**:
   - 150 learning resource URLs across 30 course topics, independently labeled by 2 raters with documented justifications (inter-rater agreement Cohen's kappa $\kappa = 1.0000$).
   - 90 high-quality references (`good`) and 60 low-quality, paywalled, or pirated links (`bad`).
3. **Q&A Benchmark (`eval/benchmark.jsonl`)**:
   - 20 evaluation test cases covering: 10 standard queries (`normal`), 4 unanswerable queries (`missing_knowledge`), 3 data privacy tests (`privacy`), and 3 safety tests (`safety`).
   - All source references strictly use the `<filename>#<page>` format, where `<page>` represents the physical document index starting at 1.
4. **Red-Team Defensive Fixtures (`eval/fixtures/redteam/`)**:
   - 15 static HTML prompt injection payloads (system prompt extraction, privilege escalation, rating bias, token theft).
   - 20 known pirated/shadow-library domains (`pirated_urls.jsonl`).
   - 10 synthetic PII-contaminated syllabus files (`pii_syllabi/`).

---

## 4. Defect Severity Matrix

| Severity | Definition | Target Resolution Window | QA Action |
| --- | --- | --- | --- |
| **Blocker** | Critical failure breaking the core loop, credential leakage, multi-tenant IDOR access, or cyclic roadmap generation. | Within 24 hours | File high-priority issue with labels `bug` and `blocker`; notify development team immediately. |
| **Major** | Functional defect affecting core business logic (e.g. schedule overlaps with busy blocks, missing CLO extractions, false-negative link filters) with available workaround. | Within current sprint/week | File issue under the active milestone; supply automated regression test case reproducing the failure. |
| **Minor** | Cosmetic display issues, minor phrasing improvements, or non-blocking UI discrepancies. | Next sprint | Log in weekly QA report bug table for backlog scheduling. |

---

## 5. Weekly QA Lifecycle

1. **Monday**: Review sprint milestone issues, align use case acceptance criteria, and update test plan specifications.
2. **Tuesday – Thursday**: Review peer pull requests, build independent integration and E2E regression tests, and execute daily CI checks.
3. **Friday**: Gather automated test counts, benchmark metrics, and execution latency numbers; publish official report to `docs/notes/qa/reports/week-N.md`.
