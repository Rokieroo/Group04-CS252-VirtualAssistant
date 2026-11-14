"""Whole-course concepts from a syllabus (#97): grounded, merged, never taken from the gold."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.concepts import extract_course_concepts, merge_similar_concepts
from app.concepts.normalize import comparison_key
from app.concepts.syllabus_concepts import enumerated, topic_parts
from app.llm import FakeLLM
from app.roadmap.builder import build_roadmap, propose_prerequisites
from app.roadmap.graph import would_create_cycle
from app.syllabus import preview_syllabus

EVAL = Path(__file__).resolve().parents[1] / "eval"
SYLLABI = EVAL / "syllabus"
GRAPHS = EVAL / "graphs"
CYCLE_CHECK_BUDGET_MS = 10.0


def concepts_of(name: str) -> tuple[list[dict], list[str]]:
    pages = [(SYLLABI / name).read_text(encoding="utf-8")]
    return extract_course_concepts(preview_syllabus(pages, None).parsed, pages), pages


def test_csc10014_gives_at_least_30_concepts_each_quoted_from_its_page():
    concepts, pages = concepts_of("01_csc10014_problem_framing.txt")

    assert len(concepts) >= 30
    assert len({c["slug"] for c in concepts}) == len(concepts)
    for concept in concepts:
        assert concept["source_page"] in concept["source_pages"]
        assert concept["quote"] in " ".join(pages[0].split())


def test_every_benchmark_concept_is_read_from_its_syllabus():
    """The extractor may not know a concept the syllabus does not state (verify or drop)."""
    for path in sorted(SYLLABI.glob("*.txt")):
        concepts, pages = concepts_of(path.name)
        text = f" {comparison_key(pages[0])} "
        assert concepts, path.name
        for concept in concepts:
            key = comparison_key(concept["title"])
            assert all(f" {w} " in text for w in key.split()), (path.name, concept["title"])
            assert key.split()[0] not in {"midterm", "final", "exam"}, concept["title"]


def test_topic_lines_split_into_listed_parts_only():
    assert topic_parts("Stacks, Queues, and Applications in Parsing.") == [
        "Stacks", "Queues", "Applications in Parsing"]
    assert topic_parts("Divide and Conquer") == ["Divide and Conquer"]
    assert topic_parts("Sorting: MergeSort (stable, O(n log n)), QuickSort") == [
        "Sorting", "MergeSort (stable, O(n log n))", "QuickSort"]
    assert enumerated("Apply graph algorithms (BFS, DFS, and Dijkstra) over (TCP).") == [
        "BFS", "DFS", "Dijkstra"]


SYLLABUS = """Course: Algorithms
- CLO1: Apply graph search (BFS, DFS, Bellman-Ford).
Week 1: Graph Representation, Breadth-First Search (BFS)
Week 2: Depth-First Search (DFS), Midterm Exam (Graphs)
"""
PARSED = {
    "weeks": [
        {"week": 1, "source_page": 1,
         "topics": ["Graph Representation, Breadth-First Search (BFS)"]},
        {"week": 2, "source_page": 1,
         "topics": ["Depth-First Search (DFS), Midterm Exam (Graphs)"]},
    ],
    "outcomes": [{"code": "clo1", "text": "Apply graph search (BFS, DFS, Bellman-Ford).",
                  "source_page": 1}],
}


def test_outcome_items_join_the_schedule_concept_they_name():
    concepts = {c["title"]: c for c in extract_course_concepts(PARSED, [SYLLABUS])}

    assert set(concepts) == {"Graph Representation", "Breadth-First Search (BFS)",
                             "Depth-First Search (DFS)", "Bellman-Ford"}
    assert concepts["Breadth-First Search (BFS)"]["aliases"] == ["BFS"]
    assert concepts["Depth-First Search (DFS)"]["clo_codes"] == ["CLO1"]
    assert concepts["Bellman-Ford"]["week"] == 1  # no week names it: the first week
    assert concepts["Bellman-Ford"]["quote"].startswith("- CLO1:")


class LiveLLM:
    """A FakeLLM counts as offline, so this wrapper stands in for a configured model."""

    def __init__(self, responses):
        self.fake = FakeLLM(responses)

    def complete(self, *args, **kwargs):
        return self.fake.complete(*args, **kwargs)


def test_a_model_concept_absent_from_the_page_is_dropped():
    answer = json.dumps({"concepts": [
        {"slug": "bellman-ford", "title": "Bellman-Ford", "summary": "s",
         "bloom_level": "apply", "source_pages": [1]},
        {"slug": "a-star", "title": "A* Search", "summary": "s",
         "bloom_level": "apply", "source_pages": [1]},
    ]})

    concepts = extract_course_concepts(
        {"weeks": [], "outcomes": []}, [SYLLABUS], llm=LiveLLM({"[Page 1]": answer}))

    assert [c["title"] for c in concepts] == ["Bellman-Ford"]


class Vectors:
    def __init__(self, vectors):
        self.vectors = vectors

    def prepare(self, texts):
        pass

    def encode(self, text):
        return self.vectors[text]


def test_embedding_merge_needs_a_shared_word_and_keeps_every_citation():
    concepts = [
        {"title": "Breadth-First Search", "week": 2, "source_pages": [2], "clo_codes": ["CLO1"]},
        {"title": "BFS", "week": 1, "source_pages": [1], "clo_codes": ["CLO2"]},
        {"title": "Search order", "week": 3, "source_pages": [3], "clo_codes": []},
    ]
    encoder = Vectors({c["title"]: [1.0, 0.0] for c in concepts})  # all embed alike

    merged = merge_similar_concepts(concepts, encoder=encoder)

    # "BFS" shares no word with "Breadth-First Search": embeddings alone never merge.
    assert [c["title"] for c in merged] == ["Breadth-First Search", "BFS"]
    assert merged[0]["aliases"] == ["Search order"]
    assert merged[0]["source_pages"] == [2, 3]
    assert merged[0]["week"] == 2
    assert "aliases" not in concepts[0]  # inputs untouched
    assert merge_similar_concepts(concepts, encoder=None) is concepts


def test_low_confidence_strict_edges_become_suggestions_on_known_nodes():
    answer = {"prerequisites": [
        {"parent_slug": "framing", "child_slug": "ladder", "confidence": 0.95, "reason": "r1"},
        {"parent_slug": "ladder", "child_slug": "requirements", "confidence": 0.5, "reason": "r2"},
        {"parent_slug": "ghost", "child_slug": "ladder", "confidence": 0.4, "reason": "r3"},
    ]}
    topics = [
        {"slug": "framing", "title": "Problem Framing", "week": 1},
        {"slug": "ladder", "title": "Solution Ladder", "week": 1},
        {"slug": "requirements", "title": "Functional Requirements", "week": 2},
    ]
    proposed = propose_prerequisites(FakeLLM({"candidates": json.dumps(answer)}), topics)
    assert [(e.confidence, e.reason) for e in proposed][:2] == [(0.95, "r1"), (0.5, "r2")]

    roadmap = build_roadmap(topics, prereq_edges=proposed)

    assert [(e.parent, e.child) for e in roadmap.edges if e.kind == "strict"] == [
        ("framing", "ladder")]
    assert [(e.parent, e.child) for e in roadmap.suggested_edges] == [("ladder", "requirements")]


def test_would_create_cycle_on_the_five_reference_graphs():
    for path in sorted(GRAPHS.glob("*.gold.json")):
        edges = json.loads(path.read_text(encoding="utf-8"))["edges"]
        pairs = [(e["parent"], e["child"]) for e in edges]
        for i, (parent, child) in enumerate(pairs):
            started = time.perf_counter()
            assert would_create_cycle(pairs[:i] + pairs[i + 1:], parent, child) is None
            assert would_create_cycle(pairs, child, parent) is not None, path.name
            assert (time.perf_counter() - started) * 1000 < 2 * CYCLE_CHECK_BUDGET_MS
