"""Placement test: which concepts an experienced learner can skip (UC-17, issue #166).

Pure graph logic: no HTTP, SQL or LLM. The caller asks a quoted, cited exercise for
the concept :func:`place` ranks first, marks the answer against the source's key and
calls :func:`place` again with the answer added.

Invariant: the known set is prerequisite-closed. A concept is known only when every
prerequisite (``strict`` edge, at any depth) is known too, so a wrong answer, a
skipped concept or an untested ancestor beyond ``INFER_DEPTH`` keeps it unknown.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.roadmap.graph import (
    PREREQUISITE_KINDS,
    _unique_ids,
    edge_kind,
    edge_pair,
    topological_sort,
)

MAX_QUESTIONS = 10
# A right answer vouches for prerequisites at most two edges up: the learner used
# them to answer, but a distant ancestor is a guess and must be asked instead.
INFER_DEPTH = 2


@dataclass(frozen=True)
class Placement:
    known: frozenset[str]  # answered right or inferred, prerequisite-closed
    tested: frozenset[str]  # the part of ``known`` the learner answered right
    unknown: frozenset[str]  # answered wrong
    candidates: tuple[str, ...]  # what to ask next, best first; empty when done


class _Graph:
    """Prerequisite parents and children of the given nodes, in study order."""

    def __init__(self, nodes: Iterable[Any], edges: Iterable[Any]):
        ids = _unique_ids(nodes)
        present = set(ids)
        pairs = [
            pair
            for edge in edges
            if edge_kind(edge) in PREREQUISITE_KINDS
            and (pair := edge_pair(edge))[0] in present
            and pair[1] in present
            and pair[0] != pair[1]
        ]
        self.parents: dict[str, set[str]] = {key: set() for key in ids}
        self.children: dict[str, set[str]] = {key: set() for key in ids}
        for parent, child in pairs:
            self.parents[child].add(parent)
            self.children[parent].add(child)
        # A node on a cycle has no place in the order and is never known.
        self.order = topological_sort(ids, pairs)

    def reach(
        self, start: str, links: Mapping[str, set[str]], depth: int | None = None
    ):
        """Nodes reachable from ``start`` through ``links``, within ``depth`` steps."""
        seen, queue = set(), deque([(start, 0)])
        while queue:
            key, steps = queue.popleft()
            if depth is not None and steps == depth:
                continue
            for nxt in links[key] - seen:
                seen.add(nxt)
                queue.append((nxt, steps + 1))
        return seen

    def closed(self, claimed: set[str]) -> set[str]:
        """The largest part of ``claimed`` whose every prerequisite is in it."""
        known: set[str] = set()
        for key in self.order:  # parents come first, so one pass is enough
            if key in claimed and self.parents[key] <= known:
                known.add(key)
        return known


def place(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    answers: Mapping[str, bool],
    skipped: Iterable[str] = (),
    known: Iterable[str] = (),
) -> Placement:
    """The known set after ``answers`` and the concepts still worth asking.

    ``known`` is what the learner already knew before this test; it is not asked.
    ``skipped`` are concepts with no markable exercise: never asked, never guessed.
    Candidates exclude anything already settled: answered, known by inference, or
    below a wrong answer (it cannot be known while that prerequisite is not).
    """
    graph = _Graph(nodes, edges)
    right = {key for key, ok in answers.items() if ok and key in graph.parents}
    unknown = {key for key, ok in answers.items() if not ok and key in graph.parents}
    claimed = right | set(known)
    for key in right:
        claimed |= graph.reach(key, graph.parents, INFER_DEPTH)
    closed = graph.closed(claimed - unknown)
    settled_so_far = Placement(
        frozenset(closed), frozenset(right & closed), frozenset(unknown), ()
    )
    if len(answers) >= MAX_QUESTIONS:
        return settled_so_far

    blocked = set(unknown)
    for key in unknown:
        blocked |= graph.reach(key, graph.children)
    settled = blocked | claimed | set(answers) | set(skipped)
    position = {key: index for index, key in enumerate(graph.order)}

    def priority(key):
        # Each answer must settle a lot either way: a right one infers ``above``, a
        # wrong one rules out ``below``. Among equals, ask first what most concepts
        # depend on (the issue's rule); then study order, so the test is repeatable.
        below = graph.reach(key, graph.children) - settled
        above = graph.reach(key, graph.parents, INFER_DEPTH) - settled
        return -min(len(above), len(below)), -len(below), position[key]

    candidates = sorted(
        (key for key in graph.order if key not in settled), key=priority
    )
    return replace(settled_so_far, candidates=tuple(candidates))


def mark_known(nodes: Iterable[Any], edges: Iterable[Any], known: set[str], node: str):
    """The known set after the learner says they know ``node``: its prerequisites too."""
    graph = _Graph(nodes, edges)
    return graph.closed(known | {node} | graph.reach(node, graph.parents))


def mark_unknown(
    nodes: Iterable[Any], edges: Iterable[Any], known: set[str], node: str
):
    """The known set after the learner says they do not know ``node``: nor what needs it."""
    graph = _Graph(nodes, edges)
    return graph.closed(known - {node} - graph.reach(node, graph.children))
