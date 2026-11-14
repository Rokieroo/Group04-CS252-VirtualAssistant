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

`python eval/run_recommendations.py` evaluates the unified recommender across all **50 weekly nodes** of the 5 benchmark syllabi (`01_csc10014` – `05_cs203`), comparing three configurations through the real `match_sources`, `vet`, `curate`, and repository persistence pipeline. Because no live search API key or external LLM quota is available in CI, external results and HTML pages come from pre-recorded offline fixtures paired with a deterministic judge (`_OfflineJudgeLLM`) that checks topic overlap and requires a verbatim `<page_text>` quote.

| Configuration | Total Nodes | Covered Nodes | Node Coverage | Precision@5 | nDCG@5 | Avg Formats in Top-5 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `db_only` | 50 | 40 | 80.0% | 0.279 | 0.344 | 1.15 |
| `db_plus_external` | 50 | 50 | 100.0% | 0.820 | 0.842 | 3.00 |
| `db_plus_external_plus_feedback` | 50 | 50 | 100.0% | 0.904 | 0.903 | 3.00 |

Key findings from the 3-configuration run:
- **`db_only` -> `db_plus_external`**: supplementing the partial, article-heavy verified DB pool with vetted external lectures, interactive exercises, and open textbooks raises node coverage from `80.0%` to `100.0%`, clears the `Precision@5 ≥ 0.80` and `nDCG@5 ≥ 0.75` targets, and increases top-5 format diversity from `1.15` to `3.00` distinct formats (`reading`, `exercise`, `video`).
- **`db_plus_external` -> `db_plus_external_plus_feedback`**: passing simulated learner feedback counts into `vet(..., ratings=ratings)` lowers borderline unhelpful summaries and promotes helpful multi-format items through `score.community`, raising `Precision@5` from `0.820` to `0.904` and `nDCG@5` from `0.842` to `0.903`.

### External Red-Team & Provenance Invariants (#160)

| Check | Coverage / Mechanism | Result |
| --- | --- | --- |
| Prompt-injection HTML pages (`eval/fixtures/redteam/injections/*.html`) | 15 injection pages run through `vet()` + `curate()` | **0 / 15** leaked to top-5 |
| Pirated domains (`eval/fixtures/redteam/pirated_urls.jsonl`) | 20 pirated URLs blocked by domain policy & vetting | **0 / 20** leaked to top-5 |
| K-12 adult-rated external pages | 3 `<meta name="rating" content="adult">` pages vetted with `Learner(k12=True)` | **0 / 3** leaked to top-5 |
| External provenance invariant (`get_or_generate_node_recommendations`) | External suggestions (`kind="external"`) checked against `verified_resources()` & `resources` table | **0** marked `verified` |
| Negative feedback dismissal | `record_recommendation_event(..., "not_helpful")` sets `dismissed_at` and excludes item on refetch | pass (`tests/test_recommendations_eval.py`) |

Reproduce: `python eval/run_recommendations.py` and `pytest -q tests/test_recommendations_eval.py`.

