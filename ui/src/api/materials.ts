import { call } from "./backend";

// Spec 12.1 and #114: the learner's own pages on a roadmap node, shown before
// verified catalog sources. Only the real backend has them; the demo has none.

export type RankedSource = {
  kind: "user_material" | "catalog" | "web";
  id: string;
  source_id?: string | null;
  institution?: string | null;
  license?: string;
  duration_min?: number | null;
  verification_status?: string;
  score?: number;
  title: string;
  url: string | null;
  pages: number[];
  provider: string;
  format: string;
  reason: string;
};
export type NodeSources = {
  node_id: string;
  status: "ready" | "insufficient";
  user_material_count: number;
  sources: RankedSource[];
};
export type MaterialPage = {
  source_id: string;
  page: number;
  confidence: number;
  method: "auto" | "manual";
};
/** Pages of one file on one node: attached, or suggested and awaiting one tap. */
export type MaterialFile = {
  file_name: string;
  status: "attached" | "suggested";
  pages: MaterialPage[];
};

const node = (id: string) => `/roadmap-nodes/${encodeURIComponent(id)}`;

export function nodeSources(nodeId: string): Promise<NodeSources> {
  return call<NodeSources>(`/concepts/${encodeURIComponent(nodeId)}/sources`);
}

export async function nodeMaterials(nodeId: string): Promise<MaterialFile[]> {
  return (await call<{ files: MaterialFile[] }>(`${node(nodeId)}/materials`))
    .files;
}

/** One tap confirms (or rejects) every page of a suggestion. */
export async function decideMaterial(
  nodeId: string,
  file: MaterialFile,
  attached: boolean,
): Promise<void> {
  for (const page of file.pages)
    await call(
      `${node(nodeId)}/materials/${encodeURIComponent(page.source_id)}`,
      {
        method: "PUT",
        body: JSON.stringify({ attached }),
      },
    );
}

/** "2–3, 7": consecutive pages read as one range. */
export function pageRanges(pages: number[]): string {
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const ranges: string[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const start = sorted[i];
    while (sorted[i + 1] === sorted[i] + 1) i++;
    ranges.push(start === sorted[i] ? `${start}` : `${start}–${sorted[i]}`);
  }
  return ranges.join(", ");
}
