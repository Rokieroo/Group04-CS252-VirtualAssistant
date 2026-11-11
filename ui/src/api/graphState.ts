import type { FilterState } from "../components/GraphFilterBar";
import type { RoadmapGraphNode } from "./graph";
import type { Edge } from "./core";
export const defaultGraphFilters: FilterState = {
  search: "",
  weekMin: 1,
  weekMax: 52,
  status: "all",
  clo: "",
  verifiedOnly: false,
  hideSoftEdges: false,
  transitiveReduction: false,
  selectedMilestone: "",
  isLocalGraph: false,
  localDepth: 2,
  viewMode: "graph",
};
const prefix = "kg_";
export function readGraphState(search = window.location.search) {
  const q = new URLSearchParams(search),
    f = { ...defaultGraphFilters };
  for (const key of ["search", "clo", "selectedMilestone"] as const)
    f[key] = q.get(prefix + key) || "";
  const status = q.get(prefix + "status");
  if (
    [
      "all",
      "mastered",
      "in_progress",
      "review_due",
      "not_started",
      "locked",
      "available",
    ].includes(status || "")
  )
    f.status = status as FilterState["status"];
  for (const key of ["weekMin", "weekMax", "localDepth"] as const) {
    const value = Number(q.get(prefix + key));
    if (
      Number.isInteger(value) &&
      value >= 1 &&
      value <= (key === "localDepth" ? 3 : 52)
    )
      f[key] = value;
  }
  f.weekMax = Math.max(f.weekMin, f.weekMax);
  for (const key of [
    "verifiedOnly",
    "hideSoftEdges",
    "transitiveReduction",
    "isLocalGraph",
  ] as const)
    f[key] = q.get(prefix + key) === "1";
  if (q.get(prefix + "viewMode") === "list") f.viewMode = "list";
  return {
    filters: f,
    selected: q.get(prefix + "node"),
    layout:
      q.get(prefix + "layout") === "force"
        ? ("force" as const)
        : ("week" as const),
  };
}
export function writeGraphState(
  filters: FilterState,
  selected: string | null,
  layout: string,
) {
  const url = new URL(window.location.href);
  for (const key of [...url.searchParams.keys()])
    if (key.startsWith(prefix)) url.searchParams.delete(key);
  for (const [key, value] of Object.entries(filters)) {
    if (value !== defaultGraphFilters[key as keyof FilterState])
      url.searchParams.set(
        prefix + key,
        typeof value === "boolean" ? (value ? "1" : "0") : String(value),
      );
  }
  if (selected) url.searchParams.set(prefix + "node", selected);
  if (layout !== "week") url.searchParams.set(prefix + "layout", layout);
  if (url.href !== window.location.href)
    window.history.replaceState(null, "", url);
}
export function topologicalNodes<
  T extends { id: string; week?: number | null; title: string },
>(nodes: T[], edges: { parent_id: string; child_id: string }[]): T[] {
  const byId = new Map(nodes.map((n) => [n.id, n])),
    degree = new Map(nodes.map((n) => [n.id, 0])),
    next = new Map<string, string[]>();
  for (const e of edges) {
    if (!byId.has(e.parent_id) || !byId.has(e.child_id)) continue;
    degree.set(e.child_id, degree.get(e.child_id)! + 1);
    next.set(e.parent_id, [...(next.get(e.parent_id) || []), e.child_id]);
  }
  const compare = (a: T, b: T) =>
      (a.week ?? 1) - (b.week ?? 1) ||
      a.title.localeCompare(b.title) ||
      a.id.localeCompare(b.id),
    queue = nodes.filter((n) => degree.get(n.id) === 0).sort(compare),
    result: T[] = [];
  while (queue.length) {
    const n = queue.shift()!;
    result.push(n);
    for (const id of next.get(n.id) || []) {
      degree.set(id, degree.get(id)! - 1);
      if (degree.get(id) === 0) {
        queue.push(byId.get(id)!);
        queue.sort(compare);
      }
    }
  }
  return [
    ...result,
    ...nodes.filter((n) => !result.some((r) => r.id === n.id)).sort(compare),
  ];
}
export function filterGraphNodes(nodes: RoadmapGraphNode[], f: FilterState) {
  return nodes.filter(
    (n) =>
      (!f.search.trim() ||
        n.title
          .toLocaleLowerCase()
          .includes(f.search.trim().toLocaleLowerCase())) &&
      (n.week ?? 1) >= f.weekMin &&
      (n.week ?? 1) <= f.weekMax &&
      (f.status === "all" || n.status === f.status) &&
      (!f.clo || n.clo?.includes(f.clo)) &&
      (!f.verifiedOnly ||
        (n.verified_sources_count ?? n.sources_count ?? 0) > 0),
  );
}
