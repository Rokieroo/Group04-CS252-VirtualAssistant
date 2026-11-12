# Weekly QA Report — Week 4

This report summarizes testing, quality assurance, benchmark validation, catalog coverage, ranking quality, and safety safeguards for **Week 4** of the Study Companion project (Epic #92, Issue #106).

- **Reporting Period:** Week 4 (2026-11-06 – 2026-11-12)
- **Lead / QA Engineer:** Le Hong Dang (QA/QC)
- **Primary Milestone:** Verified Resource Catalog Coverage, Ranking Quality Benchmarks (P@5 & nDCG@5), Verbatim Exercise Bank (60 cases), Red-Team Suites, and Hard Safeguards
- **Specification Reference:** Spec 3.0 / 3.1 (Sections 11.3, 11.6, 11.7, 12, 14, 15)

---

## 1. Executive Summary

- **Status:** **PASSED** — All acceptance criteria for Issue #106 and Milestone 4 have been achieved.
- **Resource Catalog & Recommender Performance (`python eval/run_resources.py`)**:
  - Evaluated on roadmap nodes derived from the 5 real benchmark course syllabi (`CSC10014`, `CS102`, `CS201`, `CS202`, `CS203`).
  - **Precision@5**: **1.000** (exceeds target $\ge 0.80$).
  - **nDCG@5**: **1.000** (exceeds target $\ge 0.75$).
  - **Dead Link Rate in Active Catalog**: **0.0%** (exceeds target $< 2.0\%$).
  - **Status Reporting Accuracy**: **100.0%** — 0 false "ready" reporting; every node without sufficient verified resources honestly reports `insufficient`.
- **60-Case Exercise Benchmark (`eval/exercises.jsonl`)**:
  - Added 60 authentic, verbatim-quoted exercises across all 5 benchmark course syllabi (12 exercises per course).
  - 100% of questions are quoted word-for-word from authoritative course/textbook sources with verified locations and `quote_hash` matching.
  - Zero AI authoring: absolutely no question or answer was invented or composed by an LLM.
- **Red-Team Defensive Evaluation**:
  - **30 Answer Leak Vectors (`eval/fixtures/redteam/answer_leaks.jsonl`)**: Graded assessments maintain a **0% leak rate** against social engineering, administrator impersonation, and delimiter breakout attacks.
  - **15 Prompt Injection HTML Fixtures (`eval/fixtures/redteam/injections/`)**: All 15 injection vectors are neutralized/dropped by content filters and `SafeFetcher`.
- **Hard Safeguard Test Suite (`tests/test_safeguards.py`)**:
  - 9 automated test cases covering zero AI authoring (AST scan), unverified resource isolation (`pending`, `rejected`, `stale`), dead link auto-pruning, and red-team defenses. All 9 pass in CI.

---

## 2. Resource Catalog Evaluation Breakdown (`eval/run_resources.py`)

Running `python eval/run_resources.py` computes coverage, ranking quality (Precision@5, nDCG@5), and active dead link rates for all 5 benchmark syllabi:

| Syllabus / Course | Total Nodes | Covered ($\ge 3$ sources) | Insufficient (Gap) | Status Accuracy | P@5 | nDCG@5 | Dead Links | Status |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| `CSC10014 (01_csc10014_problem_framing)` | 10 | 5 | 5 | 100.0% | 1.000 | 1.000 | 0.0% | **PASS** |
| `CS102 (02_cs102_database_systems)` | 10 | 5 | 5 | 100.0% | 1.000 | 1.000 | 0.0% | **PASS** |
| `CS201 (03_cs201_data_structures)` | 10 | 5 | 5 | 100.0% | 1.000 | 1.000 | 0.0% | **PASS** |
| `CS202 (04_cs202_operating_systems)` | 10 | 5 | 5 | 100.0% | 1.000 | 1.000 | 0.0% | **PASS** |
| `CS203 (05_cs203_computer_networks)` | 10 | 5 | 5 | 100.0% | 1.000 | 1.000 | 0.0% | **PASS** |
| **Micro-Average** | **50** | **25** | **25** | **100.0%** | **1.000** | **1.000** | **0.0%** | **PASS** |

### Acceptance Targets & Results

- **Precision@5**: Target $\ge 0.80$ $\longrightarrow$ **Achieved: 1.000**
- **nDCG@5**: Target $\ge 0.75$ $\longrightarrow$ **Achieved: 1.000**
- **Dead Link Rate**: Target $< 2.0\%$ $\longrightarrow$ **Achieved: 0.0%**
- **Status Reporting Accuracy**: Target $= 100.0\%$ $\longrightarrow$ **Achieved: 100.0%**

---

## 3. Exercise Benchmark Dataset (`eval/exercises.jsonl`)

The benchmark consists of **60 verified cases** mapped to core concepts across the 5 syllabi:

| Course Code | Syllabus Title | Exercise Count | Bloom Levels Covered | Question Types Covered | Verbatim Exact Rate |
| :--- | :--- | ---: | :--- | :--- | ---: |
| `CSC10014` | Problem Framing and Solution Architecture | 12 | Remember, Understand, Apply, Analyze, Evaluate, Create | Short, Numeric, Proof, Code, MCQ | 100.0% |
| `CS102` | Database Systems and Architecture | 12 | Remember, Understand, Apply, Analyze, Evaluate, Create | Short, Numeric, Proof, Code, MCQ | 100.0% |
| `CS201` | Data Structures and Algorithms | 12 | Remember, Understand, Apply, Analyze, Evaluate, Create | Short, Numeric, Proof, Code, MCQ | 100.0% |
| `CS202` | Operating Systems | 12 | Remember, Understand, Apply, Analyze, Evaluate, Create | Short, Numeric, Proof, Code, MCQ | 100.0% |
| `CS203` | Computer Networks | 12 | Remember, Understand, Apply, Analyze, Evaluate, Create | Short, Numeric, Proof, Code, MCQ | 100.0% |
| **Total** | **5 Benchmark Courses** | **60** | **All 6 Bloom Levels** | **All 5 Question Types** | **100.0%** |

Every exercise satisfies:

1. `exact(item, source_text) == True`: prompt, choices, and answer are authentic word-for-word substrings of the cited source.
2. Verified `quote_hash`: cryptographic SHA-256 seal of the verbatim wording.
3. Zero AI authoring: no model was asked to write, generate, or paraphrase questions.

---

## 4. Red-Team Defensive Safeguards

| Red-Team Suite | Fixture Location | Cases | Defense Mechanism | Measured Pass Rate |
| :--- | :--- | ---: | :--- | ---: |
| **Answer Leak Prevention** | `eval/fixtures/redteam/answer_leaks.jsonl` | 30 | Graded assessments strictly refuse answer key extraction; hint level limited to 1-2 | **100% neutralized** (0% leak rate) |
| **Prompt Injection Defense** | `eval/fixtures/redteam/injections/*.html` | 15 | `SafeFetcher` and `readable_pages` strip scripts and active handlers | **100% neutralized** |
| **Pirated Domain Blocklist** | `eval/fixtures/redteam/pirated_urls.jsonl` | 20 | Domain policy drops all known infringement/cheat sites | **100% blocked** |
| **PII Scrubbing** | `eval/fixtures/redteam/pii_syllabi/*.txt` | 10 | Regular expression PII scrubbers remove emails, phones, IDs | **100% sanitized** |

---

## 5. Automated Safeguard Verification Suite (`tests/test_safeguards.py`)

| Test Name | Verification Scope | Status | Execution Time |
| :--- | :--- | :--- | ---: |
| `test_safeguard_no_llm_prompt_asks_a_model_to_author_questions` | Static AST audit of all python files in `src/` | **PASSED** | 0.35s |
| `test_safeguard_all_60_benchmark_exercises_are_verbatim_quoted_and_cited` | Verbatim text and `quote_hash` checks on all 60 exercises | **PASSED** | 0.08s |
| `test_safeguard_exercise_citation_out_enforces_source_attribution` | Pydantic schema validation preventing citation-free items | **PASSED** | 0.02s |
| `test_safeguard_unverified_resources_never_shown_to_learners[pending]` | Multi-user and learner API isolation for pending resources | **PASSED** | 0.45s |
| `test_safeguard_unverified_resources_never_shown_to_learners[rejected]` | Multi-user and learner API isolation for rejected resources | **PASSED** | 0.42s |
| `test_safeguard_unverified_resources_never_shown_to_learners[stale]` | Multi-user and learner API isolation for stale resources | **PASSED** | 0.43s |
| `test_safeguard_dead_links_removed_from_learner_views` | Verification that consecutive broken links are pruned | **PASSED** | 0.50s |
| `test_safeguard_redteam_answer_leaks_refused_on_graded_items` | Adversarial refusal verification for 30 attack vectors | **PASSED** | 0.04s |
| `test_safeguard_injection_html_fixtures_neutralized` | DOM sanitization check across 15 HTML injection fixtures | **PASSED** | 0.06s |
