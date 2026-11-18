"""Regression and fast-path tests for graph layer calculation and 300-node graph assembly."""

from __future__ import annotations

from app.roadmap.graph import Edge, layers


def test_layers_single_pass_handles_mixed_edges_and_skips_soft_bumps():
    """layers computes prerequisite depths cleanly in one edge traversal per call."""
    nodes = [
        {"id": "t1", "week": 1},
        {"id": "t2", "week": 1},
        {"id": "t3", "week": 1},
        {"id": "m1", "week": 2},
    ]
    edges = [
        {"parent": "t1", "child": "t2", "kind": "strict"},
        Edge(parent="t1", child="t3", kind="soft"),
        {"parent": "t2", "child": "m1", "kind": "covers"},
        {"parent": "unknown", "child": "t1", "kind": "strict"},
    ]

    result = layers(nodes, edges)
    assert result["t1"] == 1
    assert result["t2"] == 2
    assert result["t3"] == 1  # soft edge never forces layer bump
    assert result["m1"] == 3  # milestone pushed after covered topic at layer 2


def test_layers_reads_its_edges_once():
    """One pass over the edges (#103): a one-shot iterator gives the same layers as a list."""
    # Listed last-first, so the layers are only right if the edges order the walk.
    nodes = [{"id": f"n{i}", "week": 1} for i in reversed(range(10))]
    edges = [{"parent": f"n{i}", "child": f"n{i + 1}"} for i in range(9)]
    assert layers(nodes, iter(edges)) == {f"n{i}": i + 1 for i in range(10)}
