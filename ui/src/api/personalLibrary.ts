import { call } from "./backend";
export type SourceState = "none" | "pinned" | "hidden";
export type LibraryItem = {
  url?: string | null;
  page?: number | null;
  node_id: string;
  node_title: string;
  course_id: string;
  course_title: string;
  roadmap_id: string;
  source_key: string;
  title: string;
  state: SourceState;
  note: string;
};
export function editLibrary(
  node: string,
  source_key: string,
  change: { state?: SourceState; note?: string },
) {
  return call<void>(`/concepts/${encodeURIComponent(node)}/library`, {
    method: "PATCH",
    body: JSON.stringify({ source_key, ...change }),
  });
}
