"""Regression and fast-path tests for graph layer calculation and 300-node graph assembly."""

from __future__ import annotations

from app.roadmap import graph as graph_mod
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


def test_layers_invokes_edge_pair_once_per_edge(monkeypatch):
    """layers avoids a second _adjacency/topological_sort pass over edges."""
    calls = 0
    orig = graph_mod.edge_pair

    def _counting(edge):
        nonlocal calls
        calls += 1
        return orig(edge)

    monkeypatch.setattr(graph_mod, "edge_pair", _counting)
    nodes = [{"id": f"n{i}", "week": (i // 5) + 1} for i in range(40)]
    edges = [
        {"parent": f"n{i}", "child": f"n{i + 1}", "kind": "strict" if i % 3 == 0 else "soft"}
        for i in range(39)
    ]
    layers(nodes, edges)
    assert calls == len(edges)
