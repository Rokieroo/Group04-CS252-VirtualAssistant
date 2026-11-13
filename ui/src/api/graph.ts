import { call } from "./backend";
import type { Edge } from "./core";
export type RoadmapGraphEdge = Omit<Edge, "kind" | "origin"> & {
  kind: Edge["kind"] | "covers";
  origin: Edge["origin"] | "milestone_covers";
};

export interface RoadmapGraphNode {
  id: string;
  title: string;
  type: "topic" | "milestone";
  week?: number | null;
  layer?: number | null;
  est_minutes?: number;
  outcome_ids?: string[];
  source_pages?: number[];
  sources_count?: number;
  verified_sources_count?: number;
  status?:
    | "not_started"
    | "in_progress"
    | "mastered"
    | "review_due"
    | "locked"
    | "available";
  sources_status?: "sufficient" | "insufficient" | "pending";
  clo?: string[];
  covers?: string[];
  x?: number;
  y?: number;
  pinned?: boolean;
}

export interface RoadmapGraphResponse {
  nodes: RoadmapGraphNode[];
  edges: RoadmapGraphEdge[];
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
  return normalizeGraph(
    await call<RawGraph>(
      `/roadmaps/${encodeURIComponent(roadmapId)}/graph${query}`,
    ),
  );
}

/**
 * Client-side Transitive Reduction algorithm (matching Python's transitive_reduction).
 * For a DAG, if a -> b -> c and a -> c, edge a -> c is redundant and hidden.
 */
export function computeTransitiveReduction<
  T extends { parent_id: string; child_id: string },
>(nodes: Array<{ id: string }>, edges: T[]): T[] {
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
 * Like the backend's learning_path, soft (week-order) edges are not prerequisites.
 */
export function computeMilestoneScope(
  milestoneId: string,
  nodes: Array<{ id: string; covers?: string[] }>,
  edges: RoadmapGraphEdge[],
): Set<string> {
  const milestone = nodes.find((n) => n.id === milestoneId);
  const targetIds = new Set<string>([milestoneId]);

  // Include covered topics
  if (milestone?.covers) {
    milestone.covers.forEach((c: string) => targetIds.add(c));
  }
  edges.forEach((e) => {
    if (e.child_id === milestoneId && e.kind === "covers") {
      targetIds.add(e.parent_id);
    }
  });

  // Traverse backwards to collect all prerequisites
  const reverseAdj = new Map<string, string[]>();
  edges.forEach((e) => {
    if (e.kind === "soft") return;
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
  edges: RoadmapGraphEdge[],
): { nodeIds: Set<string>; edges: RoadmapGraphEdge[] } {
  const forwardAdj = new Map<string, string[]>();
  const reverseAdj = new Map<string, string[]>();

  edges.forEach((e) => {
    if (!forwardAdj.has(e.parent_id)) forwardAdj.set(e.parent_id, []);
    forwardAdj.get(e.parent_id)!.push(e.child_id);

    if (!reverseAdj.has(e.child_id)) reverseAdj.set(e.child_id, []);
    reverseAdj.get(e.child_id)!.push(e.parent_id);
  });

  const subgraphNodes = new Set<string>([centerId]);

  const known = new Set(nodes.map((n) => n.id));
  let frontier = known.has(centerId) ? [centerId] : [];
  if (!known.has(centerId)) subgraphNodes.clear();
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const id of frontier) {
      const adjacent = [
        ...(direction !== "ancestors" ? forwardAdj.get(id) || [] : []),
        ...(direction !== "descendants" ? reverseAdj.get(id) || [] : []),
      ];
      for (const neighbor of adjacent)
        if (known.has(neighbor) && !subgraphNodes.has(neighbor)) {
          subgraphNodes.add(neighbor);
          next.push(neighbor);
        }
    }
    frontier = next;
    if (!frontier.length) break;
  }

  const subgraphEdges = edges.filter(
    (e) => subgraphNodes.has(e.parent_id) && subgraphNodes.has(e.child_id),
  );

  return { nodeIds: subgraphNodes, edges: subgraphEdges };
}

export type NodePosition = {
  node_id: string;
  x: number;
  y: number;
  pinned: boolean;
};
export async function fetchGraphLayout(id: string) {
  return (
    await call<{ positions: NodePosition[] }>(
      `/roadmaps/${encodeURIComponent(id)}/graph/layout`,
    )
  ).positions;
}
export async function saveGraphLayout(id: string, positions: NodePosition[]) {
  return call(`/roadmaps/${encodeURIComponent(id)}/graph/layout`, {
    method: "PUT",
    body: JSON.stringify({ positions }),
  });
}

type RawGraph = {
  nodes: (Omit<RoadmapGraphNode, "status" | "sources_status"> & {
    status?: string;
    sources_status?: string;
    source_count?: number;
    user_material_count?: number;
    duration_minutes?: number | null;
  })[];
  edges: (Partial<RoadmapGraphEdge> & { parent?: string; child?: string })[];
};
export function normalizeGraph(raw: RawGraph): RoadmapGraphResponse {
  return {
    nodes: raw.nodes.map((n) => ({
      ...n,
      est_minutes: n.est_minutes ?? n.duration_minutes ?? undefined,
      clo: n.clo ?? n.outcome_ids ?? [],
      sources_count: n.sources_count ?? n.source_count ?? 0,
      // Catalog counts include private uploads, which are not verified catalog sources.
      verified_sources_count:
        n.verified_sources_count ??
        Math.max(
          0,
          (n.sources_count ?? n.source_count ?? 0) -
            (n.user_material_count ?? 0),
        ),
      status: (
        {
          completed: "mastered",
          done: "mastered",
          mastered: "mastered",
          pending: "not_started",
          available: "available",
          locked: "locked",
          in_progress: "in_progress",
          needs_review: "review_due",
          review_due: "review_due",
        } as Record<string, RoadmapGraphNode["status"]>
      )[n.status || ""],
      sources_status:
        n.sources_status === "ready" || n.sources_status === "sufficient"
          ? "sufficient"
          : n.sources_status === "insufficient"
            ? "insufficient"
            : "pending",
    })),
    edges: raw.edges.map((e) => ({
      parent_id: e.parent_id ?? e.parent ?? "",
      child_id: e.child_id ?? e.child ?? "",
      kind: e.kind || "strict",
      origin: e.origin || "user",
      confidence: e.confidence ?? 1,
      ...(e.reason ? { reason: e.reason } : {}),
    })),
  };
}
