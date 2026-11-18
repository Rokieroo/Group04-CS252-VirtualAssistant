# Weekly QA Report — Week 3 (Knowledge Graph, Issue #112 / #67)

Testing, benchmark data, and invariants for **Week 3** of the Study Companion project (Knowledge Graph extraction, prerequisite edges, DAG cycle prevention, and 300-node graph performance).

- **Reporting Period:** Week 3 (Knowledge Graph & Concept DAG, Issue #112)
- **Lead / QA Engineer:** Le Hong Dang (QA/QC)
- **Specification Reference:** Spec 3.0 / 3.1 (Concept Extraction, Prerequisite Graph, DAG Invariants)

---

## 1. Benchmark Results Across 5 Gold Syllabi (`eval/run_graph.py`)

Evaluated on the 5 reference syllabi (`CSC10014`, `CS102`, `CS201`, `CS202`, `CS203`) in offline mode (`python eval/run_graph.py` — no live LLM key in CI, so concepts are derived from week topics + CLO lists and no strict edges are proposed offline):

| ID | Course | Concepts (TP/Gold) | Concept Recall | Concept Prec | Concept F1 | Strict Edges (TP/Pred/Gold) | Strict Prec | Strict Recall | Strict F1 | Kappa | Unsourced |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| KG-01 | CSC10014 | 27/30 | 0.90 | 0.79 | 0.84 | 0/0/24 | 0.00 | 0.00 | 0.00 | 0.958 | 0 |
| KG-02 | CS102 | 9/15 | 0.60 | 0.53 | 0.56 | 0/0/13 | 0.00 | 0.00 | 0.00 | 0.897 | 0 |
| KG-03 | CS201 | 9/14 | 0.64 | 0.36 | 0.46 | 0/0/14 | 0.00 | 0.00 | 0.00 | 1.000 | 0 |
| KG-04 | CS202 | 10/11 | 0.91 | 0.38 | 0.54 | 0/0/9 | 0.00 | 0.00 | 0.00 | 1.000 | 0 |
| KG-05 | CS203 | 8/9 | 0.89 | 0.29 | 0.43 | 0/0/8 | 0.00 | 0.00 | 0.00 | 1.000 | 0 |

### Aggregate Metrics
- **Micro-averaged (`offline_fake`):** Concept Recall = **0.797**, Concept Precision = **0.485**, Concept F1 = **0.603**
- **Strict Edges (`offline_fake`):** Precision = **0.000**, Recall = **0.000**, F1 = **0.000** *(expected offline: `propose_prerequisites` does not emit strict edges without `--llm`)*
- **Inter-rater Cohen's kappa:** `min = 0.897`, `mean = 0.971` (target `>= 0.70`), recomputed from the `rater_a` / `rater_b` labels stored in each `eval/graphs/*.gold.json`. **The files do not record who the raters were or that they labelled independently, so this kappa is self-reported.** #112 still needs a second team member to re-label at least one graph blind.
- **Concept precision is low because extracted parts are finer than gold concepts** ("Stacks", "Queues" against "Stacks, Queues, and Applications in Parsing"); nothing in the harness reads the gold graphs.
- **Citation coverage:** `0` unsourced concepts (`100%` of extracted concepts cite a syllabus `source_page`)
- **DAG invariant:** `0` cycles after graph construction across all 5 courses

---

## 2. Cycle Prevention & Canvas / Graph Performance

| Check | Command / Target | Measured Result | Status |
| --- | --- | --- | --- |
| `would_create_cycle` (300-node DAG, 743 edges, 100 checks) | `python eval/run_graph.py` (`< 10.0 ms`) | `mean = 0.473 ms`, `p95 = 0.766 ms`, `max = 0.950 ms` | **Pass** |
| Graph & concept API/unit tests (cycle `409 Conflict`, extraction, eval) | `pytest -q tests/test_graph_eval.py tests/test_concepts.py tests/test_roadmap_graph_api.py` | 48 tests: 48 / 48 in the full SQLite run on `main` `3e4f97d` (2026-11-18); 47 / 48 in the author's run | **Pass, 1 timing-sensitive test** |
| `GET /api/v1/roadmaps/{id}/graph` on 300-node DAG (`sqlite`) | `test_graph_performance_300_nodes[sqlite]` (`p95 < 300.0 ms`) | passed in the 2026-11-18 run; `p95 = 357.1 ms` in the author's run | **Flaky on laptops** |
| Learner B cannot read or change learner A's graph, layout, edges or mastery | `tests/test_roadmap_graph_api.py::test_graph_and_layout_user_isolation` | 404 / 403 on every graph endpoint | **Pass** |
| Canvas: upload → graph → node shows syllabus page; cycle edge blocked and red; 30- and 100-node pan/zoom FPS | `ui/e2e/graph.spec.ts` (`PLAYWRIGHT_CHANNEL=chrome pnpm run test:e2e`) | passed on the desktop project in the 2026-11-18 run on `main` `3e4f97d` (the FPS check asserts ≥ 24 FPS; the measured value is attached to the Playwright report, not recorded here) | **Pass** |

---

## 3. Open Bugs & Known Limitations

1. **Offline vs `--llm` evaluation:** `eval/run_graph.py` reports `Overall status: FAIL` in offline mode because strict prerequisite edges (`>= 0.80` precision target) and full concept recall (`>= 0.90` target) require a live LLM run (`python eval/run_graph.py --llm`).
2. **300-node SQLite `GET /graph` latency:** `test_graph_performance_300_nodes[sqlite]` has a 300 ms budget and passes or fails depending on the laptop and its load (357.1 ms in one run, a pass in another).
3. **Self-reported kappa:** see section 1; a blind second labelling of one gold graph is still owed to #112.
4. **The `--llm` run** (concept recall ≥ 0.90, strict precision ≥ 0.80) is unmeasured: it needs free-tier Gemini quota.

Reproduce:
```bash
python eval/run_graph.py
python -m pytest -q tests/test_graph_eval.py tests/test_concepts.py tests/test_roadmap_graph_api.py
```
