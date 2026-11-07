import { call } from "./backend";
import type { NodeResources, Resource } from "./types";

/** GET /roadmap-nodes/{node_id}/resources (spec 8.6) */
export async function fetchNodeResources(nodeId: string): Promise<NodeResources> {
  return call<NodeResources>(`/roadmap-nodes/${encodeURIComponent(nodeId)}/resources`);
}

/** POST /roadmap-nodes/{node_id}/resources:search (spec 8.5) */
export async function searchNodeResources(nodeId: string): Promise<{ run_id: string }> {
  return call<{ run_id: string }>(
    `/roadmap-nodes/${encodeURIComponent(nodeId)}/resources:search`,
    { method: "POST" },
  );
}

/** POST /resources/{resource_id}/feedback (spec 8.7) */
export async function sendResourceFeedback(
  resourceId: string,
  data: { node_id: string; helpful: boolean; reason?: string },
): Promise<{ status: "ok"; replacement: Resource | null }> {
  return call<{ status: "ok"; replacement: Resource | null }>(
    `/resources/${encodeURIComponent(resourceId)}/feedback`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
}
