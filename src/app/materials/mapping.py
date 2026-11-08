"""Which roadmap node each page of a learner's own material teaches (#114).

Pure functions over page texts and node titles; persistence lives in the backend.

1. Evidence: BM25 with the material's pages as the corpus and each node's title as
   the query, so words that run through the whole file weigh little. A semantic
   encoder, when configured, adds cosine similarity.
2. Sequence: slides and chapters come in sections, so a hidden Markov model whose
   state is "the node this page teaches" smooths evidence along the file. Forward-
   backward gives every page a posterior; the best node's posterior is the confidence.
3. Decision: an optional LLM reads the outline of the whole file once and settles
   the pages left below review (see ``segmenter``).

Deterministic evidence is never trusted on its own: its confidence stays below
REVIEW, so the learner confirms those pages with one tap.
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from app.retrieval.bm25 import Bm25Index, _PositiveIdfBM25

log = logging.getLogger(__name__)

REVIEW = 0.6  # below this the learner confirms; same threshold as subject tags (#99)
DETERMINISTIC_CAP = 0.59
STAY = 0.9  # prior that the next page teaches the same node as this one
BM25_SCALE = 10.0  # raw BM25 points per unit of evidence; calibrated on CSC10014 slides
SEMANTIC_WEIGHT = 2.0
REPEATED = 0.3  # a line on more than this share of pages is a header or footer


@dataclass(frozen=True)
class Node:
    id: str
    title: str


@dataclass(frozen=True)
class PageMatch:
    page: int  # 1-based, as stored in ``sources.page``
    node_id: str
    confidence: float
    method: str  # lexical | embedding | llm


def strip_repeated_lines(pages: list[str]) -> list[str]:
    """Pages without the headers and footers repeated across the file.

    Digits are masked first, so "Page 7" and "Page 8" count as the same line.
    """

    def key(line):
        return re.sub(r"\d+", "#", line.strip())

    counts = Counter(k for page in pages for k in {key(line) for line in page.splitlines()})
    limit = max(2, REPEATED * len(pages))
    return [
        "\n".join(
            line for line in page.splitlines() if line.strip() and counts[key(line)] <= limit
        )
        for page in pages
    ]


def map_pages(pages, nodes, *, embedding=None, llm=None) -> list[PageMatch]:
    """One match per page that teaches something; pages with no text get none.

    ``embedding`` is an encoder with ``prepare``/``encode`` as in
    ``app.llm.embeddings``; ``llm`` an ``LLMClient``. Either may be None.
    """
    nodes = list(nodes)
    if not nodes or not pages:
        return []
    pages = strip_repeated_lines(pages)
    vectors = _vectors(embedding, pages, nodes)
    posteriors = _posteriors([_emission(row) for row in _evidence(pages, nodes, vectors)])
    method = "embedding" if vectors else "lexical"
    matches = {}
    for number, (text, posterior) in enumerate(zip(pages, posteriors, strict=True), 1):
        if text.strip():
            best = max(range(len(nodes)), key=posterior.__getitem__)
            confidence = round(min(DETERMINISTIC_CAP, posterior[best]), 3)
            matches[number] = PageMatch(number, nodes[best].id, confidence, method)
    if llm is not None and any(m.confidence < REVIEW for m in matches.values()):
        from app.materials.segmenter import segment

        for number, decision in segment(llm, pages, nodes).items():
            if decision is None:
                matches.pop(number, None)  # the model says the page teaches no node
            else:
                matches[number] = decision
    return [matches[number] for number in sorted(matches)]


def _vectors(embedding, pages, nodes):
    """(page vectors, node vectors) from a semantic encoder, or None to stay lexical."""
    if embedding is None:
        return None
    try:
        embedding.prepare([p for p in pages if p.strip()] + [n.title for n in nodes])
        return (
            [embedding.encode(p) if p.strip() else None for p in pages],
            [embedding.encode(n.title) for n in nodes],
        )
    except (ValueError, RuntimeError, ImportError, KeyError) as exc:
        log.warning("material_embedding_unavailable error=%s", type(exc).__name__)
        return None


def _evidence(pages, nodes, vectors) -> list[list[float]]:
    """Per page, per node: how strongly the page speaks about the node."""
    index = Bm25Index(pages, model=_PositiveIdfBM25)
    lexical = [index.scores(node.title) for node in nodes]  # per node, per page
    rows = []
    for i in range(len(pages)):
        row = [lexical[k][i] / BM25_SCALE for k in range(len(nodes))]
        if vectors and vectors[0][i] is not None:
            page = vectors[0][i]
            similarity = [sum(a * b for a, b in zip(page, node)) for node in vectors[1]]
            mean = sum(similarity) / len(similarity)
            # Only how much closer the page is to one node than to the others counts.
            row = [r + SEMANTIC_WEIGHT * (s - mean) for r, s in zip(row, similarity)]
        rows.append(row)
    return rows


def _emission(row: list[float]) -> list[float]:
    """Softmax: a page with no evidence is equally likely under every node."""
    top = max(row)
    weights = [math.exp(value - top) for value in row]
    total = sum(weights)
    return [w / total for w in weights]


def _posteriors(emissions: list[list[float]]) -> list[list[float]]:
    """Forward-backward with a "stay, or move to any other node" transition.

    Moving is equally likely to every other node, so each step costs O(nodes)
    instead of O(nodes²); probabilities are renormalised per step instead of logs.
    """
    n = len(emissions[0])
    if n == 1:
        return [[1.0] for _ in emissions]
    move = (1 - STAY) / (n - 1)

    def normalised(values):
        total = sum(values)
        return [v / total for v in values]

    forward, alpha = [], [1 / n] * n
    for emission in emissions:
        alpha = normalised(
            [emission[k] * (STAY * alpha[k] + move * (1 - alpha[k])) for k in range(n)]
        )
        forward.append(alpha)
    backward, beta = [[1.0] * n], [1.0] * n
    for emission in reversed(emissions[1:]):
        weighted = [emission[k] * beta[k] for k in range(n)]
        total = sum(weighted)
        beta = normalised([STAY * w + move * (total - w) for w in weighted])
        backward.append(beta)
    backward.reverse()
    return [
        normalised([a * b for a, b in zip(alpha, beta, strict=True)])
        for alpha, beta in zip(forward, backward, strict=True)
    ]
