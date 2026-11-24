"""Issue #102 done-when: CSC10014 coverage, blind Precision@5 and ``sources:summary`` p95."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_node_sources import (
    COVERAGE_TARGET,
    P95_BUDGET_MS,
    PRECISION_TARGET,
    build_summary_load,
    evaluate_coverage,
    evaluate_precision,
    labelled_nodes,
    measure_latency,
    percentile,
    select_sources,
)


def test_csc10014_roadmap_is_covered_and_the_rest_says_insufficient():
    """Epic #92: >= 90% of the real roadmap's topics covered, the others honest."""
    coverage = evaluate_coverage()
    assert coverage.nodes == 10  # one topic per week of the CSC10014 schedule
    assert coverage.covered_rate >= COVERAGE_TARGET
    assert coverage.misleading == 0  # never "ready" under the three-source bar
    assert coverage.unverified_shown == 0
    assert coverage.passed


def test_selection_never_reads_the_labels():
    """Flipping every label leaves the chosen sources unchanged, so scoring is blind."""
    cases = labelled_nodes()
    flipped = [
        {**case, "resources": [
            {**row, "label": "bad" if row["label"] == "good" else "good", "reason": ""}
            for row in case["resources"]
        ]}
        for case in cases
    ]
    assert select_sources(flipped) == select_sources(cases)


def test_precision_at_5_on_the_labelled_benchmark_nodes():
    """Every labelled source a node shows is a good one (judged precision).

    Strict precision also counts a source no label of the node covers as wrong; those
    are other weeks' labelled pages, so strict stays under the target until #106 labels
    what the matcher shows. The floor stops a regression without hiding the gap; it was
    0.6 until the sample gained CSC10014's week 4-9 sources (#94), which #106 never
    labelled (11 unjudged shown, strict 0.594, judged still 1.0). Scoring subject
    overlap from the narrower side lifted strict to 0.676 (14 unjudged shown).
    """
    precision = evaluate_precision()
    assert precision.nodes == 25  # 5 benchmark syllabi x 5 labelled weeks
    assert precision.judged >= PRECISION_TARGET
    assert precision.strict >= 0.65


def test_percentile_is_nearest_rank():
    assert percentile([5.0, 1.0, 3.0, 2.0, 4.0], 0.5) == 3.0
    assert percentile([float(i) for i in range(1, 21)], 0.95) == 19.0


def test_summary_p95_for_40_nodes_and_300_sources(app, client, headers, clock):
    """Every source shares the roadmap's subject and topic: the costliest pool per node.

    Runs on PostgreSQL in CI (``PATHLY_TEST_DATABASE_URL``) as well as SQLite.
    """
    roadmap = build_summary_load(client, headers, app.state.database.sessions, clock[0])
    path = f"/api/v1/roadmaps/{roadmap}/sources:summary"
    nodes = client.get(path, headers=headers).json()["nodes"]
    assert len(nodes) == 40 and all(n["source_count"] == 5 for n in nodes)
    latency = measure_latency(lambda: client.get(path, headers=headers).status_code, "test")
    assert latency.p95_ms < P95_BUDGET_MS, latency


@pytest.mark.parametrize("runs", [1, 20])
def test_measure_latency_reports_every_run(runs):
    calls = []
    latency = measure_latency(lambda: calls.append(1) or 200, "stub", runs=runs, warmup=2)
    assert len(calls) == runs + 2 and latency.runs == runs
