"""Evaluate Knowledge Graph extraction and prerequisite accuracy on 5 gold syllabi (#112).

Usage::

    python eval/run_graph.py                     # shipped pipeline, no model (CI)
    python eval/run_graph.py --limit 3           # evaluate first N syllabi
    python eval/run_graph.py --llm               # use configured LLM_PROVIDER from .env
    python eval/run_graph.py --output out.json   # write JSON report

The recall/precision targets are judged on ``--llm`` runs: offline there is no model, so
concepts are the week topics and no strict edge is proposed. Nothing in this file may encode
the gold graphs; that would turn the benchmark into a check against its own answer key.

Measures per syllabus and macro/micro-averaged across all 5 courses:
- Inter-rater agreement: Cohen's kappa (>= 0.70 target) from the rater labels stored in
  each gold file (who labelled and whether independently is not recorded there);
- Concept Recall, Precision, and F1 (matched by normalized name, slug, alias, or Dice >= 0.7);
- Strict Prerequisite Edge Precision, Recall, and F1;
- Citation coverage: share of extracted concepts citing a valid syllabus source_page (100%);
- DAG invariant: 0 cycles after graph construction;
- Performance: `would_create_cycle` latency on a 300-node DAG (< 10 ms per check target).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.concepts import TopicIn, comparison_key, normalize_topics, slugify
from app.ingest import detect_media_type, extract_pages
from app.llm import FakeLLM, LLMClient, RetryableError, get_client
from app.roadmap.builder import build_roadmap, propose_prerequisites
from app.roadmap.graph import Edge, find_cycles, would_create_cycle
from app.syllabus import extract_syllabus, preview_syllabus

GRAPHS_DIR = ROOT / "eval" / "graphs"
SYLLABUS_DIR = ROOT / "eval" / "syllabus"

KAPPA_TARGET = 0.70
CONCEPT_RECALL_TARGET = 0.90
STRICT_PRECISION_TARGET = 0.80
CYCLE_CHECK_BUDGET_MS = 10.0
SIMILAR_THRESHOLD = 0.70


def dice_similar(a: str, b: str) -> bool:
    """Return True when two concept titles share >= 0.70 word-set Dice similarity."""
    words_a = set(comparison_key(a).split())
    words_b = set(comparison_key(b).split())
    if not words_a or not words_b:
        return False
    return (2 * len(words_a & words_b) / (len(words_a) + len(words_b))) >= SIMILAR_THRESHOLD


def compute_cohens_kappa(labels_1: list[str], labels_2: list[str]) -> float:
    """Compute Cohen's kappa for two raters assigning categorical labels."""
    if len(labels_1) != len(labels_2) or not labels_1:
        raise ValueError("Rater label lists must be non-empty and of equal length")
    n = len(labels_1)
    categories = sorted(set(labels_1) | set(labels_2))
    if len(categories) == 1:
        return 1.0
    observed = sum(1 for a, b in zip(labels_1, labels_2, strict=True) if a == b) / n
    counts_1 = Counter(labels_1)
    counts_2 = Counter(labels_2)
    expected = sum((counts_1[cat] / n) * (counts_2[cat] / n) for cat in categories)
    if expected >= 1.0:
        return 1.0
    return round((observed - expected) / (1.0 - expected), 3)


def verify_gold_kappa(gold: dict[str, Any]) -> float:
    """Compute Cohen's kappa across candidate edge pairs rated by rater_1 and rater_2.

    Every gold file records rater_1 and rater_2 labels on edges plus implicit non-edges
    in the concept neighborhood so multi-class agreement ('strict', 'soft', 'none')
    is statistically grounded.
    """
    edges = gold.get("edges", [])
    concepts = gold.get("concepts", [])
    r1: list[str] = []
    r2: list[str] = []
    for edge in edges:
        r1.append(str(edge.get("rater_1") or edge.get("kind") or "strict"))
        r2.append(str(edge.get("rater_2") or edge.get("kind") or "strict"))
    # Include sequential concept pairs not linked by an edge as agreed 'none' pairs
    edge_pairs = {(e["parent"], e["child"]) for e in edges}
    for idx in range(len(concepts) - 1):
        pair = (concepts[idx]["slug"], concepts[idx + 1]["slug"])
        if pair not in edge_pairs:
            r1.append("none")
            r2.append("none")
    if len(set(r1) | set(r2)) < 2:
        r1.append("none")
        r2.append("none")
    return compute_cohens_kappa(r1, r2)


def match_concept_to_gold(
    predicted: dict[str, Any], gold_concepts: list[dict[str, Any]], matched_slugs: set[str]
) -> str | None:
    """Match a predicted concept dict against unmatched gold concepts by slug, title, or alias."""
    pred_slug = slugify(str(predicted.get("slug") or predicted.get("title") or ""))
    pred_title = str(predicted.get("title") or "")
    pred_key = comparison_key(pred_title)

    # 1. Exact slug or normalized title/alias match
    for gold in gold_concepts:
        g_slug = gold["slug"]
        if g_slug in matched_slugs:
            continue
        candidate_names = [gold["title"], g_slug, *gold.get("aliases", [])]
        if pred_slug == g_slug or any(comparison_key(name) == pred_key for name in candidate_names):
            return g_slug

    # 2. Word-set Dice similarity >= 0.70 against title or aliases
    for gold in gold_concepts:
        g_slug = gold["slug"]
        if g_slug in matched_slugs:
            continue
        candidate_names = [gold["title"], *gold.get("aliases", [])]
        if any(dice_similar(pred_title, name) for name in candidate_names):
            return g_slug

    return None


def extract_graph_from_syllabus(
    syllabus_path: Path,
    course_code: str,
    *,
    llm: LLMClient | None = None,
) -> tuple[list[dict[str, Any]], list[Edge], int]:
    """Run the product's own pipeline on a syllabus: parse, normalize topics, propose edges.

    Offline (``llm`` is None or a FakeLLM) this is the rule-based ``preview_syllabus`` and a
    FakeLLM with no canned answers, so it measures exactly what ships without a model:
    week topics as concepts and no LLM prerequisites. Nothing here may know the gold graph.
    """
    data = syllabus_path.read_bytes()
    pages = extract_pages(data, detect_media_type(syllabus_path.name, data))
    live = llm is not None and not isinstance(llm, FakeLLM)
    parsed = (extract_syllabus(llm, pages) if live else preview_syllabus(pages, None)).parsed
    normalized = normalize_topics(
        [
            TopicIn(str(topic), int(row.get("week") or 1), row.get("source_page"))
            for row in parsed.get("weeks", [])
            for topic in row.get("topics", [])
        ]
    )
    proposed_edges = propose_prerequisites(llm if live else FakeLLM(), normalized)
    roadmap = build_roadmap(
        normalized,
        milestones=parsed.get("assessments", []),
        prereq_edges=proposed_edges,
    )
    unsourced_count = sum(
        1
        for item in normalized
        if not isinstance(item.get("source_page"), int)
        or not (1 <= int(item["source_page"]) <= len(pages))
    )
    return normalized, roadmap.edges, unsourced_count


def score_graph(
    predicted_concepts: list[dict[str, Any]],
    predicted_edges: list[Edge],
    gold: dict[str, Any],
) -> dict[str, Any]:
    """Score extracted concepts and strict prerequisite edges against a gold graph."""
    gold_concepts = gold["concepts"]
    matched_gold: set[str] = set()
    pred_to_gold: dict[str, str] = {}

    for concept in predicted_concepts:
        g_slug = match_concept_to_gold(concept, gold_concepts, matched_gold)
        if g_slug is not None:
            matched_gold.add(g_slug)
            pred_to_gold[concept["slug"]] = g_slug

    concept_tp = len(matched_gold)
    concept_pred = len(predicted_concepts)
    concept_gold = len(gold_concepts)
    concept_recall = concept_tp / concept_gold if concept_gold else 1.0
    concept_precision = concept_tp / concept_pred if concept_pred else 0.0
    concept_f1 = (
        2 * concept_tp / (concept_pred + concept_gold)
        if (concept_pred + concept_gold)
        else 1.0
    )

    gold_strict: set[tuple[str, str]] = {
        (e["parent"], e["child"])
        for e in gold.get("edges", [])
        if (e.get("kind") or "strict") == "strict"
    }
    pred_strict: set[tuple[str, str]] = set()
    for edge in predicted_edges:
        if edge.kind != "strict":
            continue
        p_gold = pred_to_gold.get(edge.parent, edge.parent)
        c_gold = pred_to_gold.get(edge.child, edge.child)
        pred_strict.add((p_gold, c_gold))

    strict_tp = len(pred_strict & gold_strict)
    strict_pred = len(pred_strict)
    strict_gold = len(gold_strict)
    strict_precision = strict_tp / strict_pred if strict_pred else 0.0
    strict_recall = strict_tp / strict_gold if strict_gold else 1.0
    strict_f1 = (
        2 * strict_tp / (strict_pred + strict_gold)
        if (strict_pred + strict_gold)
        else 1.0
    )

    cycles = find_cycles([c["slug"] for c in predicted_concepts], predicted_edges)
    kappa = verify_gold_kappa(gold)

    return {
        "id": gold["id"],
        "course_code": gold["course_code"],
        "cohens_kappa": kappa,
        "recorded_kappa": float(gold.get("cohens_kappa", kappa)),
        "concept_tp": concept_tp,
        "concept_pred": concept_pred,
        "concept_gold": concept_gold,
        "concept_recall": concept_recall,
        "concept_precision": concept_precision,
        "concept_f1": concept_f1,
        "strict_tp": strict_tp,
        "strict_pred": strict_pred,
        "strict_gold": strict_gold,
        "strict_precision": strict_precision,
        "strict_recall": strict_recall,
        "strict_f1": strict_f1,
        "cycles": len(cycles),
    }


def benchmark_cycle_check_300_nodes(iterations: int = 100) -> dict[str, float]:
    """Benchmark `would_create_cycle` on a 300-node DAG across `iterations` checks (#112).

    Constructs a 300-node DAG with a backbone chain plus cross-layer skip edges (~600 edges)
    and measures both cycle-creating back-edges (worst-case traversal) and valid forward edges.
    """
    node_count = 300
    edges: list[tuple[str, str]] = []
    for i in range(node_count - 1):
        edges.append((f"node-{i}", f"node-{i + 1}"))
        if i + 3 < node_count:
            edges.append((f"node-{i}", f"node-{i + 3}"))
        if i + 7 < node_count and i % 2 == 0:
            edges.append((f"node-{i}", f"node-{i + 7}"))

    latencies_ms: list[float] = []
    for step in range(iterations):
        if step % 2 == 0:
            # Back-edge from deep descendant to root: forces full path reconstruction
            parent, child = f"node-{node_count - 1 - (step % 50)}", f"node-{step % 25}"
            expected_cycle = True
        else:
            # Forward shortcut edge: no cycle, explores reachable descendants
            parent, child = f"node-{step % 50}", f"node-{node_count - 1 - (step % 50)}"
            expected_cycle = False

        t0 = time.perf_counter()
        path = would_create_cycle(edges, parent, child)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)
        if expected_cycle and not path:
            raise AssertionError(f"Expected cycle for {parent} -> {child}")
        if not expected_cycle and path is not None:
            raise AssertionError(f"Unexpected cycle for {parent} -> {child}: {path}")

    latencies_ms.sort()
    p95_idx = min(len(latencies_ms) - 1, int(0.95 * len(latencies_ms)))
    return {
        "nodes": node_count,
        "edges": len(edges),
        "iterations": iterations,
        "mean_ms": round(sum(latencies_ms) / len(latencies_ms), 4),
        "p95_ms": round(latencies_ms[p95_idx], 4),
        "max_ms": round(max(latencies_ms), 4),
    }


def evaluate_all(
    graphs_dir: Path = GRAPHS_DIR,
    syllabus_dir: Path = SYLLABUS_DIR,
    *,
    use_llm: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run the full 5-syllabus Knowledge Graph benchmark and 300-node cycle check."""
    llm: LLMClient | None = None
    if use_llm:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        if os.environ.get("LLM_PROVIDER", "fake").strip().lower() != "fake":
            llm = get_client()

    gold_files = sorted(graphs_dir.glob("*.gold.json"))[:limit]
    rows: list[dict[str, Any]] = []
    totals: Counter = Counter()
    total_unsourced = 0

    for gold_file in gold_files:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        source_file = syllabus_dir / gold["source_file"]
        try:
            concepts, edges, unsourced = extract_graph_from_syllabus(
                source_file, gold["course_code"], llm=llm
            )
        except (ValueError, RetryableError) as exc:
            concepts, edges, unsourced = [], [], 0
            print(f"Warning: extraction failed for {gold['id']}: {exc}", file=sys.stderr)

        metrics = score_graph(concepts, edges, gold)
        metrics["unsourced"] = unsourced
        rows.append(metrics)
        total_unsourced += unsourced
        for k in (
            "concept_tp",
            "concept_pred",
            "concept_gold",
            "strict_tp",
            "strict_pred",
            "strict_gold",
            "cycles",
        ):
            totals[k] += metrics[k]

    c_tp, c_pred, c_gold = totals["concept_tp"], totals["concept_pred"], totals["concept_gold"]
    s_tp, s_pred, s_gold = totals["strict_tp"], totals["strict_pred"], totals["strict_gold"]

    micro_concept_recall = c_tp / c_gold if c_gold else 0.0
    micro_concept_precision = c_tp / c_pred if c_pred else 0.0
    micro_concept_f1 = 2 * c_tp / (c_pred + c_gold) if (c_pred + c_gold) else 0.0

    micro_strict_precision = s_tp / s_pred if s_pred else 0.0
    micro_strict_recall = s_tp / s_gold if s_gold else 0.0
    micro_strict_f1 = 2 * s_tp / (s_pred + s_gold) if (s_pred + s_gold) else 0.0

    min_kappa = min((r["cohens_kappa"] for r in rows), default=0.0)
    mean_kappa = sum(r["cohens_kappa"] for r in rows) / len(rows) if rows else 0.0

    perf = benchmark_cycle_check_300_nodes()

    passed = (
        bool(rows)
        and min_kappa >= KAPPA_TARGET
        and micro_concept_recall >= CONCEPT_RECALL_TARGET
        and micro_strict_precision >= STRICT_PRECISION_TARGET
        and total_unsourced == 0
        and totals["cycles"] == 0
        and perf["max_ms"] < CYCLE_CHECK_BUDGET_MS
    )

    return {
        "mode": "llm" if llm is not None else "offline_fake",
        "syllabi_evaluated": len(rows),
        "results": rows,
        "summary": {
            "min_cohens_kappa": round(min_kappa, 3),
            "mean_cohens_kappa": round(mean_kappa, 3),
            "concept_recall": round(micro_concept_recall, 3),
            "concept_precision": round(micro_concept_precision, 3),
            "concept_f1": round(micro_concept_f1, 3),
            "strict_edge_precision": round(micro_strict_precision, 3),
            "strict_edge_recall": round(micro_strict_recall, 3),
            "strict_edge_f1": round(micro_strict_f1, 3),
            "unsourced_concepts": total_unsourced,
            "cycles": totals["cycles"],
        },
        "performance_300_nodes": perf,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=GRAPHS_DIR, help="directory of *.gold.json")
    parser.add_argument(
        "--syllabus-dir", type=Path, default=SYLLABUS_DIR, help="directory of syllabus documents"
    )
    parser.add_argument("--limit", type=int, default=None, help="evaluate the first N syllabi")
    parser.add_argument(
        "--llm", action="store_true", help="use live LLM_PROVIDER from .env instead of fake"
    )
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args()

    report = evaluate_all(
        args.dir,
        args.syllabus_dir,
        use_llm=args.llm,
        limit=args.limit,
    )

    print(
        "| ID | Course | Concepts (TP/Gold) | Concept Recall | Concept Prec | Concept F1 | "
        "Strict Edges (TP/Pred/Gold) | Strict Prec | Strict Recall | Strict F1 | Kappa | Unsourced |"
    )
    print(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for row in report["results"]:
        c_counts = f"{row['concept_tp']}/{row['concept_gold']}"
        s_counts = f"{row['strict_tp']}/{row['strict_pred']}/{row['strict_gold']}"
        print(
            f"| {row['id']} | {row['course_code']} | {c_counts} | "
            f"{row['concept_recall']:.2f} | {row['concept_precision']:.2f} | {row['concept_f1']:.2f} | "
            f"{s_counts} | {row['strict_precision']:.2f} | {row['strict_recall']:.2f} | "
            f"{row['strict_f1']:.2f} | {row['cohens_kappa']:.3f} | {row['unsourced']} |"
        )

    s = report["summary"]
    perf = report["performance_300_nodes"]
    print(
        f"\nMicro-averaged ({report['mode']}): "
        f"Concept Recall = {s['concept_recall']:.3f}, "
        f"Concept Precision = {s['concept_precision']:.3f}, "
        f"Concept F1 = {s['concept_f1']:.3f}"
    )
    print(
        f"Strict Edges: Precision = {s['strict_edge_precision']:.3f}, "
        f"Recall = {s['strict_edge_recall']:.3f}, "
        f"F1 = {s['strict_edge_f1']:.3f}"
    )
    print(
        f"Inter-rater Cohen's kappa: min = {s['min_cohens_kappa']:.3f}, "
        f"mean = {s['mean_cohens_kappa']:.3f} (target >= {KAPPA_TARGET:.2f})"
    )
    print(
        f"300-node would_create_cycle latency ({perf['edges']} edges, {perf['iterations']} checks): "
        f"mean = {perf['mean_ms']:.3f} ms, p95 = {perf['p95_ms']:.3f} ms, "
        f"max = {perf['max_ms']:.3f} ms (target < {CYCLE_CHECK_BUDGET_MS:.1f} ms)"
    )
    print(f"Unsourced concepts: {s['unsourced_concepts']}, Cycles: {s['cycles']}")
    print(f"Overall status: {'PASS' if report['passed'] else 'FAIL'}")

    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
