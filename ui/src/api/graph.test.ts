import { describe, expect, it } from "vitest";
import {
  computeTransitiveReduction,
  computeMilestoneScope,
  computeLocalSubgraph,
} from "./graph";
import type { Edge } from "./core";

describe("computeTransitiveReduction", () => {
  it("reduces transitive triangle A -> B -> C and A -> C to A -> B and B -> C", () => {
    const nodes = [{ id: "A" }, { id: "B" }, { id: "C" }];
    const edges: Edge[] = [
      { parent_id: "A", child_id: "B", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "B", child_id: "C", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "A", child_id: "C", kind: "strict", confidence: 1, origin: "week_order" }, // Redundant!
    ];

    const reduced = computeTransitiveReduction(nodes, edges);
    expect(reduced).toHaveLength(2);
    expect(reduced.some((e) => e.parent_id === "A" && e.child_id === "B")).toBe(true);
    expect(reduced.some((e) => e.parent_id === "B" && e.child_id === "C")).toBe(true);
    expect(reduced.some((e) => e.parent_id === "A" && e.child_id === "C")).toBe(false);
  });

  it("leaves already minimal DAG unchanged", () => {
    const nodes = [{ id: "A" }, { id: "B" }, { id: "C" }];
    const edges: Edge[] = [
      { parent_id: "A", child_id: "B", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "B", child_id: "C", kind: "strict", confidence: 1, origin: "week_order" },
    ];

    const reduced = computeTransitiveReduction(nodes, edges);
    expect(reduced).toHaveLength(2);
  });
});

describe("computeMilestoneScope", () => {
  it("gathers covered topics and all their ancestors for exam prep", () => {
    const nodes = [
      { id: "T1", roadmap_id: "r1", title: "Topic 1", type: "topic" as const, kind: "topic" as const },
      { id: "T2", roadmap_id: "r1", title: "Topic 2", type: "topic" as const, kind: "topic" as const },
      { id: "T3", roadmap_id: "r1", title: "Topic 3", type: "topic" as const, kind: "topic" as const },
      { id: "M1", roadmap_id: "r1", title: "Midterm", type: "milestone" as const, kind: "milestone" as const, covers: ["T2"] },
    ];

    const edges: Edge[] = [
      { parent_id: "T1", child_id: "T2", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "T2", child_id: "T3", kind: "strict", confidence: 1, origin: "week_order" },
    ];

    // Midterm covers T2; T2 has prerequisite T1. T3 is after T2 and not covered.
    const scope = computeMilestoneScope("M1", nodes, edges);
    expect(scope.has("M1")).toBe(true);
    expect(scope.has("T2")).toBe(true);
    expect(scope.has("T1")).toBe(true);
    expect(scope.has("T3")).toBe(false);
  });
});

describe("computeLocalSubgraph", () => {
  it("extracts 1-hop neighborhood around node", () => {
    const nodes = [{ id: "P" }, { id: "C" }, { id: "S" }, { id: "Far" }];
    const edges: Edge[] = [
      { parent_id: "P", child_id: "C", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "C", child_id: "S", kind: "strict", confidence: 1, origin: "week_order" },
      { parent_id: "S", child_id: "Far", kind: "strict", confidence: 1, origin: "week_order" },
    ];

    const { nodeIds, edges: subEdges } = computeLocalSubgraph("C", 1, "both", nodes, edges);
    expect(nodeIds.has("C")).toBe(true);
    expect(nodeIds.has("P")).toBe(true);
    expect(nodeIds.has("S")).toBe(true);
    expect(nodeIds.has("Far")).toBe(false);
    expect(subEdges).toHaveLength(2);
  });
});
