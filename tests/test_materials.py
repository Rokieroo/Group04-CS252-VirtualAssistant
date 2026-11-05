"""Mapping a learner's own pages onto roadmap nodes (#114), without HTTP or a database."""

import json
import sys
from pathlib import Path

from app.llm import FakeLLM
from app.materials import REVIEW, Node, PageMatch, map_pages, strip_repeated_lines

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from run_materials import score

NODES = [Node("frame", "Problem framing and stakeholders"), Node("uc", "Use case diagrams")]
FOOTER = "Dr. Tung CSC10014 Page {}"
DECK = [
    "Week 2",
    "Problem framing: who are the stakeholders?",
    "Stakeholders and their problem",
    "Recap",  # no evidence of its own: its neighbours decide
    "Problem framing traps",
    "Use case diagrams: actors",
    "Use case diagrams: include and extend",
    "",
]


def deck():
    return [f"{FOOTER.format(n)}\n{text}" for n, text in enumerate(DECK, 1)]


def test_repeated_headers_and_footers_are_dropped_even_with_page_numbers():
    assert strip_repeated_lines(deck())[1] == "Problem framing: who are the stakeholders?"
    assert strip_repeated_lines(["a\nkeep", "a\nother"]) == ["a\nkeep", "a\nother"]


def test_sections_follow_evidence_and_never_skip_review():
    matches = map_pages(deck(), NODES)
    assert [(m.page, m.node_id) for m in matches] == [
        (1, "frame"), (2, "frame"), (3, "frame"), (4, "frame"), (5, "frame"),
        (6, "uc"), (7, "uc"),
    ]  # page 8 has no text: no match
    assert all(m.method == "lexical" and m.confidence < REVIEW for m in matches)
    assert map_pages(deck(), []) == [] and map_pages([], NODES) == []
    assert {m.node_id for m in map_pages(deck(), NODES[:1])} == {"frame"}


def test_llm_decides_sections_and_its_answer_is_validated():
    answer = {
        "segments": [
            {"page_from": 1, "page_to": 1, "node": "none", "confidence": 1},
            {"page_from": 2, "page_to": 5, "node": "N1", "confidence": 0.97},
            {"page_from": 6, "page_to": 7, "node": "N2", "confidence": 0.7},
            {"page_from": 6, "page_to": 6, "node": "N1", "confidence": 1},  # overlap: ignored
            {"page_from": 0, "page_to": 9, "node": "N1", "confidence": 1},  # outside: ignored
            {"page_from": 8, "page_to": 8, "node": "N9", "confidence": 1},  # unknown node
            {"page_from": 8, "page_to": 8, "node": "N1", "confidence": True},
        ]
    }
    llm = FakeLLM({"material_outline": json.dumps(answer)})
    matches = {m.page: m for m in map_pages(deck(), NODES, llm=llm)}
    assert llm.calls == 1
    assert 1 not in matches  # the cover teaches nothing
    assert matches[2] == PageMatch(2, "frame", 0.85, "llm")  # capped below a person
    assert (matches[6].node_id, matches[6].confidence) == ("uc", 0.7)
    assert matches[3].confidence >= REVIEW


def test_a_failed_or_malformed_llm_answer_keeps_the_deterministic_matches():
    plain = map_pages(deck(), NODES)
    for bad in ("not json", "{}", '{"segments": "x"}', '{"segments": [{"page_from": 1}]}'):
        assert map_pages(deck(), NODES, llm=FakeLLM({"material_outline": bad})) == plain


class Encoder:
    """Two-dimensional "semantic" vectors: framing words point one way, use cases the other."""

    model = "fake"

    def prepare(self, texts):
        self.ready = set(texts)

    def encode(self, text):
        if text not in self.ready:
            raise KeyError(text)
        lowered = text.lower()
        return [1.0, 0.0] if "frame" in lowered or "framing" in lowered else [0.0, 1.0]


def test_semantic_vectors_add_evidence_but_still_ask_the_learner():
    pages = ["How to frame a vague need", "Actors and their goals"]
    matches = map_pages(pages, NODES, embedding=Encoder())
    assert [(m.node_id, m.method) for m in matches] == [("frame", "embedding"), ("uc", "embedding")]
    assert all(m.confidence < REVIEW for m in matches)

    class Broken(Encoder):
        def prepare(self, texts):
            raise RuntimeError("embedding_unavailable")

    assert {m.method for m in map_pages(pages, NODES, embedding=Broken())} == {"lexical"}


def test_eval_scores_only_gradable_pages():
    matches = [PageMatch(1, "a", 0.9, "llm"), PageMatch(2, "b", 0.3, "lexical")]
    ranges = [[1, 2, ["A"]], [3, 3, []]]
    assert score(matches, ranges, {"a": "A", "b": "B"}) == (1, 2, 1, 1)
