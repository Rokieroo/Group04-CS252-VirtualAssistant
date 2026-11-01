// Shapes follow spec 8.2; summary/source_pages mirror the `concepts` table columns.
export type Concept = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  bloom_level: string;
  source_file: string;
  source_pages: number[];
  confirmed: boolean;
};
export type Prereq = {
  parent_id: string;
  child_id: string;
  kind: "strict" | "soft";
  confidence: number;
};
export type Graph = { concepts: Concept[]; prereqs: Prereq[] };

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const ERRORS = {
  not_pdf: "Only PDF files are supported.",
  file_too_large: "This file is larger than 20 MB. Split or compress it first.",
  invalid_pdf: "This PDF is damaged or cannot be opened.",
  scanned_pdf:
    "No readable text in this file. You can paste the page content instead.",
  concepts_unavailable:
    "The AI could not read this file right now (busy or out of daily quota). Try again later.",
  items_unavailable:
    "The AI could not write cited questions for this concept right now. Try again later.",
  upload_in_progress: "This file is already being uploaded. Wait for it to finish.",
  cycle: "This link would create a loop. Remove one link first.",
} as const;

/** Client-side check before any upload call; returns an error key or null. */
export function checkFile(file: {
  name: string;
  size: number;
  type: string;
}): "not_pdf" | "file_too_large" | null {
  const pdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!pdf) return "not_pdf";
  if (file.size > MAX_UPLOAD_BYTES) return "file_too_large";
  return null;
}

export const rename = (g: Graph, id: string, title: string): Graph => ({
  ...g,
  concepts: g.concepts.map((c) => (c.id === id ? { ...c, title } : c)),
});

export const remove = (g: Graph, id: string): Graph => ({
  concepts: g.concepts.filter((c) => c.id !== id),
  prereqs: g.prereqs.filter((p) => p.parent_id !== id && p.child_id !== id),
});

/** Merge `dropId` into `keepId`: pages are combined, edges rerouted, self-loops and duplicates dropped. */
export function merge(g: Graph, keepId: string, dropId: string): Graph {
  const drop = g.concepts.find((c) => c.id === dropId);
  if (!drop || keepId === dropId) return g;
  const concepts = g.concepts
    .filter((c) => c.id !== dropId)
    .map((c) =>
      c.id === keepId
        ? {
            ...c,
            source_pages: [...new Set([...c.source_pages, ...drop.source_pages])].sort(
              (a, b) => a - b,
            ),
          }
        : c,
    );
  const seen = new Set<string>();
  const prereqs = g.prereqs
    .map((p) => ({
      ...p,
      parent_id: p.parent_id === dropId ? keepId : p.parent_id,
      child_id: p.child_id === dropId ? keepId : p.child_id,
    }))
    .filter((p) => {
      const key = `${p.parent_id}>${p.child_id}`;
      if (p.parent_id === p.child_id || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  return { concepts, prereqs };
}

/** True when adding parent → child would close a loop (child already reaches parent). */
export function createsCycle(
  prereqs: Prereq[],
  parentId: string,
  childId: string,
): boolean {
  const stack = [childId];
  const seen = new Set<string>();
  while (stack.length) {
    const id = stack.pop()!;
    if (id === parentId) return true;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const p of prereqs) if (p.parent_id === id) stack.push(p.child_id);
  }
  return false;
}

export function addPrereq(
  g: Graph,
  parentId: string,
  childId: string,
): Graph | { error: string } {
  if (createsCycle(g.prereqs, parentId, childId)) return { error: ERRORS.cycle };
  if (g.prereqs.some((p) => p.parent_id === parentId && p.child_id === childId))
    return g;
  return {
    ...g,
    prereqs: [
      ...g.prereqs,
      { parent_id: parentId, child_id: childId, kind: "strict", confidence: 1 },
    ],
  };
}

export const removePrereq = (g: Graph, parentId: string, childId: string): Graph => ({
  ...g,
  prereqs: g.prereqs.filter((p) => !(p.parent_id === parentId && p.child_id === childId)),
});

export const confirmAll =(g: Graph): Graph => ({
  ...g,
  concepts: g.concepts.map((c) => ({ ...c, confirmed: true })),
});
