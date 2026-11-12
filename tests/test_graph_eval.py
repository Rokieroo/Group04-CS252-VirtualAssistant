"""Tests for the 5 reference Knowledge Graphs, eval/run_graph.py, and 300-node cycle check (#112)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

from run_graph import (
    CONCEPT_RECALL_TARGET,
    CYCLE_CHECK_BUDGET_MS,
    GRAPHS_DIR,
    KAPPA_TARGET,
    STRICT_PRECISION_TARGET,
    SYLLABUS_DIR,
    benchmark_cycle_check_300_nodes,
    compute_cohens_kappa,
    evaluate_all,
    score_graph,
    verify_gold_kappa,
)

from app.roadmap.graph import Edge, find_cycles, topological_sort_or_raise
from devcli.ai import validate_graph_benchmark


def test_five_gold_graphs_validate_and_meet_inter_rater_kappa():
    """All 5 gold files in eval/graphs/ must be valid DAGs with Cohen's kappa >= 0.70."""
    errors = validate_graph_benchmark(GRAPHS_DIR)
    assert errors == [], f"Gold graph validation errors: {errors}"

    gold_files = sorted(GRAPHS_DIR.glob("*.gold.json"))
    assert len(gold_files) == 5

    for gf in gold_files:
        data = json.loads(gf.read_text(encoding="utf-8"))
        assert float(data["cohens_kappa"]) >= KAPPA_TARGET, gf.name
        assert verify_gold_kappa(data) >= KAPPA_TARGET, gf.name

        concepts = data["concepts"]
        if data["course_code"] == "CSC10014":
            assert len(concepts) >= 30, "CSC10014 gold graph must have at least 30 concepts"

        slugs = [c["slug"] for c in concepts]
        assert len(slugs) == len(set(slugs)), f"Duplicate concept slugs in {gf.name}"
        for concept in concepts:
            assert isinstance(concept.get("source_page"), int) and concept["source_page"] >= 1

        # Gold graph must be a valid DAG
        assert find_cycles(slugs, data["edges"]) == [], f"Cycle found in {gf.name}"
        order = topological_sort_or_raise(slugs, data["edges"])
        assert len(order) == len(slugs)


def test_cohens_kappa_computation():
    """Verify Cohen's kappa edge cases and partial disagreement."""
    # Perfect agreement across 3 classes
    assert compute_cohens_kappa(["strict", "soft", "none"], ["strict", "soft", "none"]) == 1.0

    # High agreement with minor disagreement (>= 0.7)
    r1 = ["strict"] * 15 + ["soft"] * 5 + ["none"] * 10
    r2 = ["strict"] * 14 + ["soft"] * 6 + ["none"] * 10
    kappa = compute_cohens_kappa(r1, r2)
    assert 0.70 <= kappa < 1.0


def test_score_graph_matches_aliases_and_strict_edges():
    """Verify concept matching by alias and strict edge precision/recall calculation."""
    gold = json.loads((GRAPHS_DIR / "01_csc10014_problem_framing.gold.json").read_text("utf-8"))
    # Construct predicted concepts using aliases where available
    predicted_concepts = [
        {
            "slug": c["slug"],
            "title": (c["aliases"][0] if c.get("aliases") else c["title"]),
            "week": c["week"],
            "source_page": c["source_page"],
        }
        for c in gold["concepts"]
    ]
    predicted_edges = [
        Edge(parent=e["parent"], child=e["child"], kind=e["kind"], confidence=e["confidence"])
        for e in gold["edges"]
    ]
    metrics = score_graph(predicted_concepts, predicted_edges, gold)
    assert metrics["concept_recall"] == 1.0
    assert metrics["concept_precision"] == 1.0
    assert metrics["strict_precision"] == 1.0
    assert metrics["strict_recall"] == 1.0
    assert metrics["cycles"] == 0


def test_run_graph_offline_evaluation_meets_all_targets():
    """Offline evaluation across all 5 syllabi must pass recall, precision, and citation targets."""
    report = evaluate_all(GRAPHS_DIR, SYLLABUS_DIR, use_llm=False)
    assert report["syllabi_evaluated"] == 5
    assert report["passed"] is True

    summary = report["summary"]
    assert summary["min_cohens_kappa"] >= KAPPA_TARGET
    assert summary["concept_recall"] >= CONCEPT_RECALL_TARGET
    assert summary["strict_edge_precision"] >= STRICT_PRECISION_TARGET
    assert summary["unsourced_concepts"] == 0
    assert summary["cycles"] == 0


def test_would_create_cycle_300_nodes_under_10ms():
    """Performance test: would_create_cycle on a 300-node DAG must complete in < 10 ms per check."""
    perf = benchmark_cycle_check_300_nodes(iterations=100)
    assert perf["nodes"] == 300
    assert perf["edges"] >= 300
    assert perf["mean_ms"] < CYCLE_CHECK_BUDGET_MS
    assert perf["p95_ms"] < CYCLE_CHECK_BUDGET_MS
    assert perf["max_ms"] < CYCLE_CHECK_BUDGET_MS

