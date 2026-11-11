// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import {
  defaultGraphFilters,
  filterGraphNodes,
  readGraphState,
  writeGraphState,
  topologicalNodes,
} from "./graphState";
import { normalizeGraph, computeLocalSubgraph } from "./graph";
afterEach(() => history.replaceState(null, "", "/"));
it("restores all URL filters, selection and layout without corrupting page hash", () => {
  history.replaceState(null, "", "/?unrelated=keep#roadmap");
  const filters = {
    ...defaultGraphFilters,
    search: "Đồ thị",
    weekMin: 3,
    weekMax: 12,
    status: "review_due" as const,
    clo: "CLO1",
    verifiedOnly: true,
    hideSoftEdges: true,
    transitiveReduction: true,
    selectedMilestone: "exam",
    isLocalGraph: true,
    localDepth: 3,
    viewMode: "list" as const,
  };
  writeGraphState(filters, "node/1", "force");
  expect(location.hash).toBe("#roadmap");
  expect(new URLSearchParams(location.search).get("unrelated")).toBe("keep");
  expect(readGraphState()).toEqual({
    filters,
    selected: "node/1",
    layout: "force",
  });
});
it("validates malformed URL values", () => {
  const state = readGraphState(
    "?kg_weekMin=NaN&kg_weekMax=999&kg_localDepth=9&kg_status=madeup",
  );
  expect(state.filters).toEqual(defaultGraphFilters);
});
it("normalizes actual server fields and applies CLO and verified-source filters", () => {
  const graph = normalizeGraph({
    nodes: [
      {
        id: "a",
        title: "A",
        type: "topic",
        week: 1,
        status: "completed",
        outcome_ids: ["CLO1"],
        source_count: 2,
        sources_status: "ready",
      },
      {
        id: "b",
        title: "B",
        type: "topic",
        week: 2,
        status: "pending",
        outcome_ids: ["CLO2"],
        source_count: 0,
      },
    ],
    edges: [{ parent: "a", child: "b", kind: "strict" }],
  });
  expect(graph.edges[0]).toMatchObject({ parent_id: "a", child_id: "b" });
  expect(graph.nodes[0]).toMatchObject({
    status: "mastered",
    sources_status: "sufficient",
    sources_count: 2,
    clo: ["CLO1"],
  });
  expect(
    filterGraphNodes(graph.nodes, {
      ...defaultGraphFilters,
      clo: "CLO1",
      verifiedOnly: true,
    }).map((n) => n.id),
  ).toEqual(["a"]);
  expect(
    filterGraphNodes(graph.nodes, {
      ...defaultGraphFilters,
      clo: "CLO2",
      verifiedOnly: true,
    }),
  ).toEqual([]);
  expect(
    normalizeGraph({
      nodes: [{ id: "x", title: "Unknown", type: "topic" }],
      edges: [],
    }).nodes[0].status,
  ).toBeUndefined();
});
it("orders prerequisites before alphabetically earlier children", () => {
  const nodes = [
    { id: "child", title: "A child", week: 1 },
    { id: "parent", title: "Z parent", week: 2 },
  ];
  expect(
    topologicalNodes(nodes, [{ parent_id: "parent", child_id: "child" }]).map(
      (n) => n.id,
    ),
  ).toEqual(["parent", "child"]);
});
it("local graph both traverses mixed directions without unrelated nodes", () => {
  const edges = [
    { parent_id: "p", child_id: "a" },
    { parent_id: "p", child_id: "b" },
  ].map((e) => ({
    ...e,
    kind: "strict" as const,
    origin: "user" as const,
    confidence: 1,
  }));
  expect(
    [
      ...computeLocalSubgraph(
        "a",
        2,
        "both",
        [{ id: "a" }, { id: "b" }, { id: "p" }, { id: "other" }],
        edges,
      ).nodeIds,
    ].sort(),
  ).toEqual(["a", "b", "p"]);
});

it("does not count personal uploads as verified catalog sources", () => {
  const graph = normalizeGraph({
    nodes: [
      {
        id: "private",
        title: "Private uploads",
        type: "topic",
        source_count: 2,
        user_material_count: 2,
        sources_status: "ready",
      },
    ],
    edges: [],
  });
  expect(graph.nodes[0].sources_count).toBe(2);
  expect(
    filterGraphNodes(graph.nodes, {
      ...defaultGraphFilters,
      verifiedOnly: true,
    }),
  ).toEqual([]);
});
