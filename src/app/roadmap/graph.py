"""Graph helpers for roadmap nodes (spec 10.1).

Kahn's algorithm gives a deterministic study order. Tarjan's algorithm finds every
strongly connected component; every edge inside such a component is part of a cycle,
so ``find_cycles`` can return the edges the user has to remove.

The public helpers accept plain node ids, ``NodeSpec`` objects, dictionaries and the
``Edge`` dataclass, because callers build graphs from normalized topics, prompt
answers and stored rows. Edges that point outside the node set are ignored.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Edge:
    """One directed prerequisite edge: ``parent`` must be studied before ``child``."""

    parent: str
    child: str
    kind: str = "strict"  # "strict" (prerequisite) or "soft" (week order)
    confidence: float = 1.0
    reason: str = ""

    @property
    def parent_slug(self) -> str:
        return self.parent

    @property
    def child_slug(self) -> str:
        return self.child

    @property
    def source(self) -> str:
        return self.parent

    @property
    def target(self) -> str:
        return self.child


def node_key(node: Any) -> str:
    """Return the stable id used by the graph for a node of any supported shape."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for key in ("id", "slug", "key", "name", "title"):
            value = node.get(key)
            if value:
                return str(value)
        return str(node)
    for attribute in ("id", "slug", "key", "name", "title"):
        value = getattr(node, attribute, None)
        if value:
            return str(value)
    return str(node)


def edge_pair(edge: Any) -> tuple[str, str]:
    """Read a ``(parent, child)`` pair from a tuple, dict, Edge or object."""
    if isinstance(edge, Edge):
        return edge.parent, edge.child
    if isinstance(edge, (tuple, list)):
        if len(edge) < 2:
            raise ValueError(f"edge needs two endpoints: {edge!r}")
        return str(edge[0]), str(edge[1])
    if isinstance(edge, dict):
        for parent, child in (
            ("parent_slug", "child_slug"),
            ("parent", "child"),
            ("source", "target"),
            ("from", "to"),
        ):
            if edge.get(parent) and edge.get(child):
                return str(edge[parent]), str(edge[child])
        raise ValueError(f"edge needs parent and child: {edge!r}")
    parent = getattr(edge, "parent", None) or getattr(edge, "source", None)
    child = getattr(edge, "child", None) or getattr(edge, "target", None)
    if parent is None or child is None:
        raise ValueError(f"edge needs parent and child: {edge!r}")
    return str(parent), str(child)


def _unique_ids(nodes: Iterable[Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        key = node_key(node)
        if key not in seen:
            seen.add(key)
            ids.append(key)
    return ids


def _adjacency(nodes: Iterable[Any], edges: Iterable[Any]) -> tuple[
    list[str], dict[str, list[str]], dict[str, int]
]:
    ids = _unique_ids(nodes)
    known = set(ids)
    adjacency: dict[str, list[str]] = {key: [] for key in ids}
    indegree: dict[str, int] = {key: 0 for key in ids}
    for edge in edges:
        parent, child = edge_pair(edge)
        if parent not in known or child not in known:
            continue
        adjacency[parent].append(child)
        indegree[child] += 1
    return ids, adjacency, indegree


def topological_sort(nodes: Iterable[Any], edges: Iterable[Any]) -> list[str]:
    """Kahn's topological order, deterministic for the given node and edge order.

    A cyclic graph has no complete order. The returned list then contains only the
    nodes Kahn could release; call :func:`find_cycles` first when the caller needs to
    explain or repair the cycle. Use :func:`topological_sort_or_raise` to reject it.
    """
    ids, adjacency, indegree = _adjacency(nodes, edges)
    ready = deque(key for key in ids if indegree[key] == 0)
    order: list[str] = []
    while ready:
        parent = ready.popleft()
        order.append(parent)
        for child in adjacency[parent]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return order


def topological_sort_or_raise(nodes: Iterable[Any], edges: Iterable[Any]) -> list[str]:
    """Kahn's order, raising ``ValueError`` with the offending edges on a cycle."""
    ids = _unique_ids(nodes)
    order = topological_sort(ids, edges)
    if len(order) != len(ids):
        cycles = find_cycles(ids, edges)
        raise ValueError(f"dependency cycle: {cycles!r}")
    return order


def strongly_connected_components(
    nodes: Iterable[Any], edges: Iterable[Any]
) -> list[list[str]]:
    """Tarjan's SCCs, each in discovery order; singleton components included."""
    ids, adjacency, _ = _adjacency(nodes, edges)
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    counter = 0

    def visit(node: str) -> None:
        nonlocal counter
        index[node] = lowlink[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for child in adjacency[node]:
            if child not in index:
                visit(child)
                lowlink[node] = min(lowlink[node], lowlink[child])
            elif child in on_stack:
                lowlink[node] = min(lowlink[node], index[child])
        if lowlink[node] != index[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(component)

    for node in ids:
        if node not in index:
            visit(node)
    return components


def find_cycles(nodes: Iterable[Any], edges: Iterable[Any]) -> list[Any]:
    """Return the input edges that belong to a dependency cycle.

    Tarjan's SCCs identify cyclic groups; all original edges whose endpoints are in
    the same cyclic component are returned in input order, so a caller can show the
    user exactly which prerequisite edges to remove. A self-loop is a cycle too.
    Original edge shapes are preserved (tuples stay tuples, ``Edge`` stays ``Edge``).
    """
    ids, adjacency, _ = _adjacency(nodes, edges)
    components = strongly_connected_components(ids, edges)
    node_to_component: dict[str, int] = {}
    for idx, component in enumerate(components):
        if len(component) > 1:
            for member in component:
                node_to_component[member] = idx
        elif len(component) == 1:
            member = component[0]
            if member in adjacency[member]:  # self-loop
                node_to_component[member] = idx

    result: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        parent, child = edge_pair(edge)
        pair = (parent, child)
        if (
            parent in node_to_component
            and child in node_to_component
            and node_to_component[parent] == node_to_component[child]
            and pair not in seen
        ):
            seen.add(pair)
            result.append(edge)
    return result


def would_create_cycle(edges: Iterable[Any], parent: str, child: str) -> list[str] | None:
    """The closed path introduced by parent → child, or None (#97/#100).

    Iterative DFS avoids recursion limits on long, valid prerequisite chains.
    """
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        start, end = edge_pair(edge)
        adjacency.setdefault(start, []).append(end)
    stack = [child]
    previous: dict[str, str | None] = {child: None}
    while stack:
        current = stack.pop()
        if current == parent:
            path = []
            while current is not None:
                path.append(current)
                current = previous[current]
            return [parent, *reversed(path)]
        for target in reversed(adjacency.get(current, [])):
            if target not in previous:
                previous[target] = current
                stack.append(target)
    return None


def transitive_reduction(
    nodes: Iterable[Any], edges: Iterable[Any]
) -> list[Any]:
    """Transitive reduction of a DAG: keeps edges with no alternate path >= 2 (#97).

    Preserves original edge items (whether tuples, dicts, or Edge objects).
    """
    node_ids = _unique_ids(nodes)
    known = set(node_ids)

    adjacency: dict[str, list[tuple[str, Any]]] = {nid: [] for nid in node_ids}
    edge_list = list(edges)
    for edge in edge_list:
        parent, child = edge_pair(edge)
        if parent in known and child in known and parent != child:
            adjacency[parent].append((child, edge))

    kept: list[Any] = []
    for parent in node_ids:
        children = adjacency[parent]
        if not children:
            continue
        if len(children) == 1:
            kept.append(children[0][1])
            continue

        redundant_children: set[str] = set()
        for w, _ in children:
            visited: set[str] = set()
            queue = deque([w])
            while queue:
                curr = queue.popleft()
                for nxt, _ in adjacency.get(curr, []):
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            for v, _ in children:
                if v != w and v in visited:
                    redundant_children.add(v)

        for v, edge in children:
            if v not in redundant_children:
                kept.append(edge)

    return kept


def local_graph(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    center_id: str,
    depth: int = 2,
    direction: str = "both",
) -> tuple[list[str], list[Any]]:
    """Return (subgraph_node_ids, subgraph_edges) within `depth` steps of `center_id` (#97)."""
    depth = max(1, min(depth, 5))
    ids = _unique_ids(nodes)
    known = set(ids)
    if center_id not in known:
        return ([center_id], []) if center_id else ([], [])

    forward_adj: dict[str, list[str]] = {nid: [] for nid in ids}
    reverse_adj: dict[str, list[str]] = {nid: [] for nid in ids}
    edge_list = list(edges)
    for edge in edge_list:
        p, c = edge_pair(edge)
        if p in known and c in known:
            forward_adj[p].append(c)
            reverse_adj[c].append(p)

    subgraph_nodes: set[str] = {center_id}

    if direction in ("descendants", "both"):
        frontier = {center_id}
        for _ in range(depth):
            next_frontier = set()
            for u in frontier:
                for v in forward_adj.get(u, []):
                    if v not in subgraph_nodes:
                        subgraph_nodes.add(v)
                        next_frontier.add(v)
            frontier = next_frontier
            if not frontier:
                break

    if direction in ("ancestors", "both"):
        frontier = {center_id}
        for _ in range(depth):
            next_frontier = set()
            for u in frontier:
                for v in reverse_adj.get(u, []):
                    if v not in subgraph_nodes:
                        subgraph_nodes.add(v)
                        next_frontier.add(v)
            frontier = next_frontier
            if not frontier:
                break

    subgraph_edges = [
        edge
        for edge in edge_list
        if edge_pair(edge)[0] in subgraph_nodes and edge_pair(edge)[1] in subgraph_nodes
    ]
    ordered_nodes = [nid for nid in ids if nid in subgraph_nodes]
    if center_id not in ordered_nodes:
        ordered_nodes.append(center_id)
    return ordered_nodes, subgraph_edges


def layers(
    nodes: Iterable[Any], edges: Iterable[Any]
) -> dict[str, int]:
    """Calculate layer for each node (spec 10.1, issue #97).

    Defaults to `week` of syllabus; pushes child to later layer if prerequisite requires it.
    """
    node_list = list(nodes)
    ids = _unique_ids(node_list)
    node_by_id = {}
    for item in node_list:
        k = node_key(item)
        if k not in node_by_id:
            node_by_id[k] = item

    def get_week(nid: str) -> int:
        item = node_by_id.get(nid)
        if item is None:
            return 1
        w = getattr(item, "week", None)
        if w is None and isinstance(item, dict):
            w = item.get("week")
        return max(1, w) if w is not None else 1

    layer_map: dict[str, int] = {nid: get_week(nid) for nid in ids}

    strict_parents: dict[str, list[str]] = {nid: [] for nid in ids}
    for edge in edges:
        p, c = edge_pair(edge)
        if p in layer_map and c in layer_map and p != c:
            kind = getattr(edge, "kind", None)
            if kind is None and isinstance(edge, dict):
                kind = edge.get("kind")
            if kind in ("strict", "covers"):
                strict_parents[c].append(p)

    order = topological_sort(ids, edges)
    for nid in order:
        for p in strict_parents.get(nid, []):
            layer_map[nid] = max(layer_map[nid], layer_map[p] + 1)

    return layer_map
