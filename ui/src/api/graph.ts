import { call } from "./backend";
import type { Edge } from "./core";
import type { RoadmapNode } from "./types";

export interface RoadmapGraphNode {
  id: string;
  title: string;
  type: "topic" | "milestone";
  week?: number | null;
  layer?: number | null;
  est_minutes?: number | null;
  status?: "not_started" | "in_progress" | "mastered" | "review_due";
  sources_status?: "sufficient" | "insufficient" | "pending";
  clo?: string[];
  covers?: string[];
  x?: number;
  y?: number;
  pinned?: boolean;
}

export interface RoadmapGraphResponse {
  nodes: RoadmapGraphNode[];
  edges: Edge[];
  center_id?: string;
  depth?: number;
}

/**
 * Fetch full roadmap graph from server.
 * GET /api/v1/roadmaps/{roadmapId}/graph?reduce={reduce}
 */
export async function fetchRoadmapGraph(
  roadmapId: string,
  reduce = false,
): Promise<RoadmapGraphResponse> {
  const query = reduce ? "?reduce=true" : "";
  return call<RoadmapGraphResponse>(`/roadmaps/${encodeURIComponent(roadmapId)}/graph${query}`);
}

/**
 * Fetch local subgraph around center node.
 * GET /api/v1/roadmap-nodes/{nodeId}/graph?depth={depth}&direction={direction}
 */
export async function fetchNodeLocalGraph(
  nodeId: string,
  depth = 2,
  direction: "both" | "ancestors" | "descendants" = "both",
): Promise<RoadmapGraphResponse> {
  const params = new URLSearchParams({
    depth: String(depth),
    direction,
  });
  return call<RoadmapGraphResponse>(
    `/roadmap-nodes/${encodeURIComponent(nodeId)}/graph?${params.toString()}`,
  );
}

/**
 * Client-side Transitive Reduction algorithm (matching Python's transitive_reduction).
 * For a DAG, if a -> b -> c and a -> c, edge a -> c is redundant and hidden.
 */
export function computeTransitiveReduction<T extends { parent_id: string; child_id: string }>(
  nodes: Array<{ id: string }>,
  edges: T[],
): T[] {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const adjacency = new Map<string, Array<{ childId: string; edge: T }>>();

  for (const n of nodes) {
    adjacency.set(n.id, []);
  }

  for (const edge of edges) {
    if (
      nodeIds.has(edge.parent_id) &&
      nodeIds.has(edge.child_id) &&
      edge.parent_id !== edge.child_id
    ) {
      if (!adjacency.has(edge.parent_id)) {
        adjacency.set(edge.parent_id, []);
      }
      adjacency.get(edge.parent_id)!.push({ childId: edge.child_id, edge });
    }
  }

  const kept: T[] = [];

  for (const n of nodes) {
    const children = adjacency.get(n.id) || [];
    if (children.length === 0) continue;
    if (children.length === 1) {
      kept.push(children[0].edge);
      continue;
    }

    const redundantChildren = new Set<string>();
    for (const { childId: w } of children) {
      const visited = new Set<string>();
      const queue = [w];
      while (queue.length > 0) {
        const curr = queue.shift()!;
        const nextHops = adjacency.get(curr) || [];
        for (const next of nextHops) {
          if (!visited.has(next.childId)) {
            visited.add(next.childId);
            queue.push(next.childId);
          }
        }
      }
      for (const { childId: v } of children) {
        if (v !== w && visited.has(v)) {
          redundantChildren.add(v);
        }
      }
    }

    for (const childItem of children) {
      if (!redundantChildren.has(childItem.childId)) {
        kept.push(childItem.edge);
      }
    }
  }

  return kept;
}

/**
 * Client-side Learning Path for milestone exam prep (covers + all prerequisites).
 */
export function computeMilestoneScope(
  milestoneId: string,
  nodes: Array<{ id: string; covers?: string[] }>,
  edges: Edge[],
): Set<string> {
  const milestone = nodes.find((n) => n.id === milestoneId);
  const targetIds = new Set<string>([milestoneId]);

  // Include covered topics
  if (milestone?.covers) {
    milestone.covers.forEach((c: string) => targetIds.add(c));
  }
  edges.forEach((e) => {
    if (e.parent_id === milestoneId && (e.kind as string) === "covers") {
      targetIds.add(e.child_id);
    }
  });

  // Traverse backwards to collect all prerequisites
  const reverseAdj = new Map<string, string[]>();
  edges.forEach((e) => {
    if (!reverseAdj.has(e.child_id)) reverseAdj.set(e.child_id, []);
    reverseAdj.get(e.child_id)!.push(e.parent_id);
  });

  const scope = new Set<string>(targetIds);
  const queue = Array.from(targetIds);

  while (queue.length > 0) {
    const curr = queue.shift()!;
    const parents = reverseAdj.get(curr) || [];
    for (const p of parents) {
      if (!scope.has(p)) {
        scope.add(p);
        queue.push(p);
      }
    }
  }

  return scope;
}

/**
 * Client-side Local Subgraph extractor.
 */
export function computeLocalSubgraph(
  centerId: string,
  depth: number,
  direction: "both" | "ancestors" | "descendants",
  nodes: Array<{ id: string }>,
  edges: Edge[],
): { nodeIds: Set<string>; edges: Edge[] } {
  const forwardAdj = new Map<string, string[]>();
  const reverseAdj = new Map<string, string[]>();

  edges.forEach((e) => {
    if (!forwardAdj.has(e.parent_id)) forwardAdj.set(e.parent_id, []);
    forwardAdj.get(e.parent_id)!.push(e.child_id);

    if (!reverseAdj.has(e.child_id)) reverseAdj.set(e.child_id, []);
    reverseAdj.get(e.child_id)!.push(e.parent_id);
  });

  const subgraphNodes = new Set<string>([centerId]);

  if (direction === "descendants" || direction === "both") {
    let frontier = [centerId];
    for (let d = 0; d < depth; d++) {
      const nextFrontier: string[] = [];
      for (const u of frontier) {
        for (const v of forwardAdj.get(u) || []) {
          if (!subgraphNodes.has(v)) {
            subgraphNodes.add(v);
            nextFrontier.push(v);
          }
        }
      }
      frontier = nextFrontier;
      if (frontier.length === 0) break;
    }
  }

  if (direction === "ancestors" || direction === "both") {
    let frontier = [centerId];
    for (let d = 0; d < depth; d++) {
      const nextFrontier: string[] = [];
      for (const u of frontier) {
        for (const v of reverseAdj.get(u) || []) {
          if (!subgraphNodes.has(v)) {
            subgraphNodes.add(v);
            nextFrontier.push(v);
          }
        }
      }
      frontier = nextFrontier;
      if (frontier.length === 0) break;
    }
  }

  const subgraphEdges = edges.filter(
    (e) => subgraphNodes.has(e.parent_id) && subgraphNodes.has(e.child_id),
  );

  return { nodeIds: subgraphNodes, edges: subgraphEdges };
}
