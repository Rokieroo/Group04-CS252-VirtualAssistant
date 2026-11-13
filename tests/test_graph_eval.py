"""Tests for the 5 reference Knowledge Graphs, eval/run_graph.py, and 300-node cycle check (#112)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

from run_graph import (
    CYCLE_CHECK_BUDGET_MS,
    GRAPHS_DIR,
    KAPPA_TARGET,
    SYLLABUS_DIR,
    benchmark_cycle_check_300_nodes,
    compute_cohens_kappa,
    evaluate_all,
    score_graph,
    verify_gold_kappa,
)

from app.concepts import extract_course_concepts, merge_similar_concepts
from app.llm import FakeLLM
from app.roadmap.builder import build_roadmap, propose_prerequisites
from app.roadmap.graph import (
    Edge,
    find_cycles,
    topological_sort_or_raise,
    would_create_cycle,
)
from app.syllabus import preview_syllabus
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


def test_run_graph_offline_scores_the_shipped_pipeline_without_an_answer_key():
    """Offline runs the rule-based parser with no model; the targets are judged on --llm runs.

    No strict edge can appear without an LLM, so any offline edge credit would mean the
    harness had learned the gold graph again.
    """
    report = evaluate_all(GRAPHS_DIR, SYLLABUS_DIR, use_llm=False)
    assert report["syllabi_evaluated"] == 5
    summary = report["summary"]
    assert summary["min_cohens_kappa"] >= KAPPA_TARGET
    assert 0.0 <= summary["concept_recall"] <= 1.0
    assert summary["strict_edge_precision"] == 0.0
    assert all(row["strict_tp"] == 0 for row in report["results"])
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


def test_csc10014_extracts_at_least_30_concepts_with_valid_citations():
    """CSC10014 demo requirement: >= 30 concepts, 100% cited with valid syllabus pages (#97)."""
    syl_path = SYLLABUS_DIR / "01_csc10014_problem_framing.txt"
    pages = [syl_path.read_text(encoding="utf-8")]
    draft = preview_syllabus(pages, None)
    concepts = extract_course_concepts(draft.parsed, pages)

    assert len(concepts) >= 30, f"Expected >= 30 concepts, got {len(concepts)}"
    for c in concepts:
        page = c.get("source_page")
        assert isinstance(page, int) and 1 <= page <= len(pages), f"Invalid page citation in {c}"
        assert c.get("slug"), f"Missing slug in {c}"
        assert c.get("title"), f"Missing title in {c}"

    # Match against gold concepts: recall must be >= 90%
    gold = json.loads((GRAPHS_DIR / "01_csc10014_problem_framing.gold.json").read_text(encoding="utf-8"))
    metrics = score_graph(concepts, [], gold)
    assert metrics["concept_recall"] >= 0.90, f"Recall too low: {metrics['concept_recall']}"


def test_all_five_reference_graphs_concept_recall_meets_target():
    """Across all 5 reference graphs, concept recall must be >= 90% with 0 unsourced concepts (#97)."""
    report = evaluate_all(GRAPHS_DIR, SYLLABUS_DIR, use_llm=False)
    assert report["syllabi_evaluated"] == 5
    summary = report["summary"]
    assert summary["concept_recall"] >= 0.90, f"Recall was {summary['concept_recall']}"
    assert summary["unsourced_concepts"] == 0
    assert summary["cycles"] == 0
    assert report["passed"]


def test_semantic_merging_with_embeddings_and_normalize():
    """Test merge_similar_concepts with mock embeddings (cosine >= 0.85)."""
    class MockEmbeddingEncoder:
        def __init__(self, vectors: dict[str, list[float]]):
            self.vectors = vectors

        def prepare(self, texts: list[str]) -> None:
            pass

        def encode(self, text: str) -> list[float]:
            return self.vectors.get(text, [1.0, 0.0])

    # Two concepts with high cosine similarity (>= 0.85)
    # [1.0, 0.0] and [0.95, 0.312] -> dot product ~ 0.95 >= 0.85
    mock_encoder = MockEmbeddingEncoder({
        "Problem Framing": [1.0, 0.0],
        "Problem Framing Methodology": [0.95, 0.3122],
        "Relational Algebra": [0.0, 1.0],
    })

    raw_concepts = [
        {"slug": "problem-framing", "title": "Problem Framing", "week": 1, "source_pages": [1], "clo_codes": ["CLO1"]},
        {"slug": "problem-framing-method", "title": "Problem Framing Methodology", "week": 2, "source_pages": [2], "clo_codes": ["CLO2"]},
        {"slug": "relational-algebra", "title": "Relational Algebra", "week": 3, "source_pages": [3], "clo_codes": ["CLO3"]},
    ]

    merged = merge_similar_concepts(raw_concepts, encoder=mock_encoder, threshold=0.85)
    assert len(merged) == 2
    framing = next(c for c in merged if c["slug"] == "problem-framing")
    assert framing["source_pages"] == [1, 2]
    assert set(framing["clo_codes"]) == {"CLO1", "CLO2"}
    assert "Problem Framing Methodology" in framing.get("aliases", [])


def test_would_create_cycle_on_five_reference_graphs():
    """Run would_create_cycle on all 5 reference graphs and measure latency (< 10 ms)."""
    import time

    for gf in sorted(GRAPHS_DIR.glob("*.gold.json")):
        gold = json.loads(gf.read_text(encoding="utf-8"))
        raw_edges = gold.get("edges", [])
        edge_pairs = [(e["parent"], e["child"]) for e in raw_edges]

        # Valid forward edges must not report cycles
        for i, (p, c) in enumerate(edge_pairs):
            other_edges = edge_pairs[:i] + edge_pairs[i + 1:]
            t0 = time.perf_counter()
            cycle = would_create_cycle(other_edges, p, c)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert elapsed_ms < CYCLE_CHECK_BUDGET_MS
            assert cycle is None, f"Unexpected cycle for forward edge {p} -> {c} in {gf.name}"

        # Reversing an edge must create a cycle
        for p, c in edge_pairs:
            t0 = time.perf_counter()
            cycle = would_create_cycle(edge_pairs, c, p)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert elapsed_ms < CYCLE_CHECK_BUDGET_MS
            assert cycle is not None, f"Expected cycle when reversing {p} -> {c} in {gf.name}"


def test_strict_edge_proposal_with_confidence_and_reason_via_llm():
    """Verify strict prerequisite proposal with confidence and reason, plus threshold filtering."""
    prereq_response = {
        "prerequisites": [
            {
                "parent_slug": "problem-framing",
                "child_slug": "solution-ladder",
                "confidence": 0.95,
                "reason": "Solution tier selection requires problem framing first.",
            },
            {
                "parent_slug": "solution-ladder",
                "child_slug": "functional-requirements",
                "confidence": 0.50,  # Below STRICT_CONFIDENCE (0.6)
                "reason": "Weak association between solution ladder and functional requirements.",
            },
        ]
    }

    mock_llm = FakeLLM({"candidates": json.dumps(prereq_response)})
    topics = [
        {"slug": "problem-framing", "title": "Problem Framing", "week": 1},
        {"slug": "solution-ladder", "title": "Solution Ladder", "week": 1},
        {"slug": "functional-requirements", "title": "Functional Requirements", "week": 2},
    ]

    proposed = propose_prerequisites(mock_llm, topics)
    assert len(proposed) == 2
    assert proposed[0].confidence == 0.95
    assert proposed[0].reason == "Solution tier selection requires problem framing first."
    assert proposed[1].confidence == 0.50

    roadmap = build_roadmap(topics, prereq_edges=proposed)
    # Accepted strict edges has confidence >= 0.6
    strict_edges = [e for e in roadmap.edges if e.kind == "strict"]
    assert len(strict_edges) == 1
    assert strict_edges[0].parent == "problem-framing"
    assert strict_edges[0].child == "solution-ladder"

    # Suggested edges holds below-threshold edges (< 0.6) for user confirmation
    assert len(roadmap.suggested_edges) == 1
    assert roadmap.suggested_edges[0].parent == "solution-ladder"
    assert roadmap.suggested_edges[0].child == "functional-requirements"
    assert roadmap.suggested_edges[0].confidence == 0.50


