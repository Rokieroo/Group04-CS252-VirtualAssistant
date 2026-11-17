# Weekly QA Report — Week 4

Testing, benchmark data and safeguards for **Week 4** of the Study Companion project (Epic #92, Issue #106): the verified catalog, ranking quality, the exercise bank and the "no AI-authored questions" rule.

- **Reporting Period:** Week 4 (2026-11-06 – 2026-11-12)
- **Lead / QA Engineer:** Le Hong Dang (QA/QC)
- **Specification Reference:** Spec 3.0 / 3.1 (Sections 11.3, 11.6, 11.7, 12, 14, 15)

---

## 1. Summary

| Item (#106) | State | Evidence |
| --- | --- | --- |
| Safeguard tests in CI: no prompt asks a model to write questions; unverified sources never reach learners | **Done, passing** | `tests/test_safeguards.py` (section 4) |
| 15 injection pages neutralized, 20 pirated URLs blocked, 10 PII syllabi produce no PII query | **Done, passing** | section 4 |
| 60-case exercise benchmark | **Fixture merged** — synthetic, see section 3 | `eval/exercises.jsonl` |
| 30 answer-leak attacks | **Fixtures merged, not run** — no hint or grading path exists yet (#163) | `eval/fixtures/redteam/answer_leaks.jsonl` |
| Coverage, Precision@5, nDCG@5, dead links on roadmaps from the 5 syllabi | **Not measured yet** | section 2 |

An earlier draft of this report showed Precision@5 = 1.000, nDCG@5 = 1.000, 100 % status accuracy, 0 % dead links and a 0 % leak rate. Those numbers came from an offline mode of `eval/run_resources.py` that kept only the candidates raters had labelled *good* and then measured how many of them were good, copied each node's expected status into its "actual" status, and from a leak test that only checked the fixture fields. None of it exercised the product, so the numbers are withdrawn and the offline mode was removed.

---

## 2. Ranking Quality (`eval/run_resources.py`)

`python eval/run_resources.py` runs the real resource finder on each labelled node of `eval/resources.jsonl` (30 nodes, labels from #66): the safe fetcher downloads every candidate, the LLM judge vets it, the curator picks what is shown. It prints Precision@5 (share of shown resources labelled good) and nDCG@5 (order of what was shown against the best order of the node's good candidates). nDCG@5 was added this week and has unit tests (`tests/test_run_resources.py`).

**Not run for this report.** A full run costs up to 12 judge calls per node and the shared free-tier Gemini key allows about 20 calls a day per model, so it has to be spread over several days (`--limit`). Until a run is recorded here, these #106 targets are unmeasured:

- Precision@5 ≥ 0.80, nDCG@5 ≥ 0.75
- Coverage on roadmaps built from the 5 benchmark syllabi (share of nodes with ≥ 3 verified sources, or an honest `insufficient`): needs those roadmaps generated against a seeded catalog; no script does that yet.
- Dead links shown to learners (< 2 %): comes from the link-check job on a real catalog, not from this dataset.

---

## 3. Exercise Benchmark Fixture (`eval/exercises.jsonl`)

60 cases, 12 per course for `CSC10014`, `CS102`, `CS201`, `CS202`, `CS203`, covering the 6 Bloom levels and 5 formats (short, numeric, proof, code, MCQ). Each case has a `source_text`, a location and a `quote_hash`; `python dev.py ai benchmark validate` and `tests/test_safeguards.py` check that the prompt, choices and answer appear verbatim in that `source_text` and that the hash matches.

**These cases are synthetic.** Each `source_text` was written together with its cases (for example one "Problems and Exercises for CSC10014" block is reused for several cases at different page numbers); none is an excerpt of a real textbook or course handout. The fixture is useful to test the matching and grading code (#115), but it cannot show that exercises shown to learners are authentic: that guarantee comes from the API, which only returns an exercise with a citation that still matches its source (`ExerciseCitationOut`, tested below).

---

## 4. Safeguard and Red-Team Tests

| Test | What it checks | Result |
| --- | --- | --- |
| `test_safeguard_no_llm_prompt_asks_a_model_to_author_questions` | AST scan of `src/`: no prompt string asks a model to write, generate or invent questions | pass |
| `test_safeguard_exercise_citation_out_enforces_source_attribution` | the API schema refuses an exercise without exactly one source | pass |
| `test_safeguard_unverified_resources_never_shown_to_learners[pending, rejected, stale]` | `verified_resources` and `CatalogSearch` never return them | pass (3) |
| `test_safeguard_dead_links_removed_from_learner_views` | a dead resource is removed from every node | pass |
| `test_safeguard_injection_html_fixtures_neutralized` | 15 injection pages leave no script or event handler in the readable text | pass |
| `test_exercise_benchmark_fixture_is_internally_consistent` | the 60-case fixture quotes its own source text, hashes match | pass |
| `test_answer_leak_fixtures_are_well_formed` | the 30 attacks target graded items and expect refusal (format only, not run) | pass |
| `tests/test_safe_fetch.py::test_twenty_pirated_urls_are_all_blocked` | 20 pirated URLs blocked by domain policy | pass |
| `tests/test_search.py::test_ten_pii_syllabi_produce_zero_pii_queries` | 10 syllabi with PII produce no outgoing query containing it | pass |

Reproduce: `python -m pytest tests/test_safeguards.py tests/test_safe_fetch.py tests/test_search.py tests/test_run_resources.py` and `python dev.py ai benchmark validate`.

---

## 5. Still Open for #106

1. A recorded `python eval/run_resources.py` run (Precision@5, nDCG@5), spread over days for the quota.
2. A script that builds roadmaps from the 5 syllabi against a seeded catalog and reports coverage.
3. Dead-link rate from the link-check job on the staging catalog.
4. Run the 30 answer-leak attacks once node hints and grading exist (#163).
5. Replace or supplement the synthetic exercises with real, licensed excerpts before using them to claim a grading agreement rate (#115: ≥ 85 % on 60 cases).

---

## 6. Unified Recommender Benchmark & External Red-Team (#160)

`python eval/run_recommendations.py` runs the 50 week nodes of the 5 benchmark syllabi through the real `match_sources`, `vet` and `curate`. No search key or model runs in CI, so external pages are **synthetic fixtures** and the judge is a stand-in (`ContentJudge`) that reads only what the real judge is shown: relevance is the share of the node's words on the page. It never sees a label. (A first version of this section reported Precision@5 0.820 / 0.904 with a judge that rejected pages containing "spam", "pirated", "dump" or "evil-exfil", words the fixtures had been written with, and with Khan Academy and edX pages as external results although ADR 004 forbids automated access to both. Those numbers measured the fixtures; they were replaced.)

| Configuration | Total Nodes | Covered Nodes | Node Coverage | Precision@5 | nDCG@5 | Avg Formats in Top-5 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `db_only` | 50 | 38 | 76.0% | 0.398 | 0.445 | 1.05 |
| `db_plus_external` | 50 | 50 | 100.0% | 0.828 | 0.873 | 3.00 |
| `db_plus_external_plus_feedback` | 50 | 50 | 100.0% | 0.892 | 0.920 | 3.00 |

How to read it:

- `db_only` is the only row with human labels behind it (#106 resources, assigned to the closest week); its low precision and 76 % coverage say the catalog pool is thin, not that matching is wrong.
- The two external rows are **pipeline checks, not quality**: the five on-topic pages per node are written to be on-topic, so precision mostly shows that vetting drops the off-topic page and keeps a thin outline (counted as not good). The feedback row uses the fixture labels as votes (an oracle), so +0.064 P@5 is an upper bound on what votes can add.
- Real recommendation quality is still **unmeasured**: it needs recorded responses from the #157 providers with blind labels, or an `--llm` run.

### External Red-Team & Provenance Invariants (#160)

Pirated and adult pages are written **on-topic**, so only the domain policy and the K-12 filter can keep them out; a control page with the same text on an ordinary host must reach the top 5 (asserted).

| Check | Result |
| --- | --- |
| K-12 adult-rated pages (`<meta name="rating" content="adult">`), `Learner(k12=True)` | **0 / 3** in top-5 |
| External recommendations marked `verified` | **0** |
| Negative feedback dismissal (`not_helpful` sets `dismissed_at`) | pass |
| Pirated URLs (`eval/fixtures/redteam/pirated_urls.jsonl`) | **FAIL: 2 in top-5** (was 5). 18 / 20 domains are now `BLOCKED`: real file lockers (mega.nz, mediafire.com, rapidgator, anonfiles), `t.me`, paste sites, warez forums, and `token:` rules for torrent hosts and bypass services named after a blocked answer dump (`chegg-…`, `coursehero-…`, `studocu-…`). `vet()` now enforces `BLOCKED` for any fetcher. Still shown: `scribd-vips.xyz` and `leaked-textbooks.ru` |
| Prompt-injection pages (15 fixtures) | **FAIL: 1 in top-5** (`inj_04`: its directive is stripped, and the on-topic sentence left is shown). Directives neutralized **10 / 15** (was 0): 3 hidden in comments, `<script>` and `onerror` are dropped by `read_document`; `strip_commands` now removes bracketed bot labels, mode switches ("maintenance mode", "unfiltered"), role spoofing (`Assistant:`), French "ignorez les instructions", "bypass safety", `{{…}}` markdown exfiltration and base64-encoded directives. Kept: SQL, "print to all students", "repeat infinitely", the false-fact page and "forget context" |

Not done on purpose: the two remaining pirated hosts and the five remaining directives were invented for this fixture set, so blocking those exact names or phrases would only fit the test set. Rules like `drop table`, `execute this query`, `and print …` and `always cite` would also strip real SQL, I/O and writing lessons; `tests/test_vetting.py` now checks that such course text survives. The two gates stay strict `xfail` in `tests/test_recommendations_eval.py`. Closing them needs a policy decision: either drop every page that tries to address the grader (this also drops security lectures that quote injections), or rely on the model and the `<page_text>` data block, measured with `--llm`.

Reproduce: `python eval/run_recommendations.py` and `pytest -q tests/test_recommendations_eval.py`.

---

## 7. Suite Totals, Known Limitations & Reproduction (#67)

- **Backend test suite (SQLite):** `pytest -q tests/` runs the full Phase 1–4 backend suite across SQLite (`test_vetting.py`, `test_safe_fetch.py`, `test_recommendations_eval.py` pass with 2 `xfail`s documented in Section 6; `test_graph_eval.py`, `test_concepts.py`, `test_roadmap_graph_api.py` pass `47 / 48` with `test_graph_performance_300_nodes[sqlite]` at `357.1 ms`). PostgreSQL parity (`PATHLY_TEST_DATABASE_URL`) is verified in CI (`postgres-integration` job in `.github/workflows/ci.yml`).
- **UI & E2E tests:** Maintained in `ui/` (`pnpm test`, `pnpm run build`, `pnpm run test:e2e`) and executed in CI (`frontend` job); `pnpm` was not installed in this local Windows shell.
- **Load test (#168):** Recorded separately in `docs/notes/qa/reports/week-4-load-test.md` (`1,000` simulated sessions at `concurrency=25` against `deploy/docker-compose.prod.yml` with `API_WORKERS=4`: `0.00%` error rate across `6,000` requests, all 5 read endpoints `p95 <= 507.4 ms`, overall `p95 = 2128.0 ms` due to `login` Argon2 contention at `2427.4 ms`).
- **Open limitations remaining across Week 4:**
  1. Live `--llm` runs for `eval/run_resources.py` and `eval/run_graph.py` require an active external LLM quota.
  2. `eval/exercises.jsonl` cases are synthetic fixtures; real licensed textbook excerpts are needed before claiming live grading agreement (`#115`).
  3. The 30 answer-leak attacks (`eval/fixtures/redteam/answer_leaks.jsonl`) are validated for schema/format in `tests/test_safeguards.py`; end-to-end execution against `#163` hint/grading paths remains open.
  4. Two strict `xfail` red-team gaps in Section 6 (`#160`) and the `login` p95 / `pg_stat_statements` items in `week-4-load-test.md` (`#168`) remain open.
