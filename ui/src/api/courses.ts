import { checkFile, type Concept, type Graph, type Prereq } from "../concepts";
import { BackendError, backendEnabled, call, session } from "./backend";

// Spec 8.1–8.2 on the real backend when VITE_BACKEND_MODE=api; otherwise a demo mock.
export type UploadResult = {
  file_name: string;
  pages: number;
  status: "processing" | "processed" | "error";
  warning?: "scanned_pdf";
};
type Code =
  | "not_pdf"
  | "file_too_large"
  | "invalid_pdf"
  | "scanned_pdf"
  | "concepts_unavailable"
  | "items_unavailable"
  | "upload_in_progress";
const CODES: readonly string[] = [
  "not_pdf",
  "file_too_large",
  "invalid_pdf",
  "scanned_pdf",
  "concepts_unavailable",
  "items_unavailable",
  "upload_in_progress",
];
export class ApiError extends Error {
  constructor(public code: Code) {
    super(code);
  }
}

/** Known backend codes become ApiError (shown from ERRORS); others keep their message. */
async function backend<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await call<T>(path, init);
  } catch (err) {
    if (err instanceof BackendError && CODES.includes(err.code)) throw new ApiError(err.code as Code);
    throw err;
  }
}

const courseIds = new Map<string, Promise<string>>();
/** The signed-in user's course with this title, created on first use. */
function courseId(title: string): Promise<string> {
  const key = `${session.get()}|${title}`;
  let id = courseIds.get(key);
  if (!id) {
    id = backend<{ id: string; title: string }[]>("/courses").then(
      async (courses) =>
        courses.find((c) => c.title === title)?.id ??
        (await backend<{ id: string }>("/courses", {
          method: "POST",
          body: JSON.stringify({ title }),
        })).id,
    );
    id.catch(() => courseIds.delete(key)); // retry the lookup next time
    courseIds.set(key, id);
  }
  return id;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A cited practice question (spec 10.2), stored as a draft for the course owner to review. */
export type Item = {
  id: string;
  type: "mcq" | "short";
  prompt: string;
  choices: string[];
  answer: string;
  rubric: string[];
  source_id: string;
  page: number;
  file_name: string;
  status: string;
};

/** Writes new questions for a stored concept and returns all of its questions (backend only). */
export async function generateItems(course: string, conceptId: string): Promise<Item[]> {
  const id = await courseId(course);
  return backend<Item[]>(
    `/courses/${id}/concepts/${encodeURIComponent(conceptId)}/items:generate`,
    { method: "POST" },
  );
}

export async function uploadSource(course: string, file: File): Promise<UploadResult> {
  const rejected = checkFile(file);
  if (rejected) throw new ApiError(rejected);
  if (backendEnabled) {
    const form = new FormData();
    form.append("file", file);
    // Slow on purpose: the vision model reads the slides before this returns.
    const result = await backend<UploadResult>(`/courses/${await courseId(course)}/sources`, {
      method: "POST",
      body: form,
    });
    return { ...result, warning: result.warning ?? undefined };
  }
  const raw = new TextDecoder("latin1").decode(await file.arrayBuffer());
  await delay(1500);
  if (!raw.startsWith("%PDF-")) throw new ApiError("invalid_pdf");
  // shortcut: no text layer usually means no fonts; the real ingest decides this server-side.
  if (!raw.includes("/Font")) throw new ApiError("scanned_pdf");
  const pages = raw.match(/\/Type\s*\/Page(?![s\w])/g)?.length ?? 0;
  return { file_name: file.name, pages, status: "processed" };
}

const WEEK1 = "CSC10014_2026_Week01_Problem_Framing.pdf";
const sample: [string, string, string, number][] = [
  ["framing-ladder", "Framing ladder", "Need → Problem → Split → Options → Success", 26],
  ["problem-statement", "Problem statement", "A template that forces clarity", 29],
  ["stakeholders", "Stakeholders", "Users are only one kind of stakeholder", 38],
  ["personas", "Personas", "Four personas, four problems", 41],
  ["jobs-to-be-done", "Jobs-to-be-Done", "When…, I want to…, so I can…", 45],
  ["four-layers", "Four layers", "User need, product goal, requirement, implementation", 52],
  ["fr-vs-nfr", "FR vs NFR", "What it does vs how well", 55],
  ["non-goals", "Non-goals", "The most underrated section of a brief", 59],
  ["solution-ladder", "Solution ladder", "Climb only as high as the problem requires", 77],
  ["product-risks", "Four product risks", "Value, usability, feasibility, viability", 101],
];

/** Concepts of the whole course after extracting `fileName` (the demo ignores both). */
export async function proposeConcepts(course: string, fileName: string): Promise<Graph> {
  if (backendEnabled) {
    const id = await courseId(course);
    const graph = await backend<{ concepts: Omit<Concept, "source_file">[]; prereqs: Prereq[] }>(
      `/courses/${id}/concepts:propose?file_name=${encodeURIComponent(fileName)}`,
      { method: "POST" },
    );
    // shortcut: concepts carry no file name yet (see save_concepts); show pages only.
    return {
      concepts: graph.concepts.map((c) => ({ ...c, source_file: "" })),
      prereqs: graph.prereqs,
    };
  }
  await delay(600);
  const concepts: Concept[] = sample.map(([slug, title, summary, page], i) => ({
    id: `c_${i + 1}`,
    slug,
    title,
    summary,
    bloom_level: "understand",
    source_file: WEEK1,
    source_pages: [page],
    confirmed: false,
  }));
  const edge = (parent: number, child: number): Prereq => ({
    parent_id: `c_${parent}`,
    child_id: `c_${child}`,
    kind: "strict",
    confidence: 0.8,
  });
  return {
    concepts,
    prereqs: [edge(1, 2), edge(3, 4), edge(6, 7), edge(2, 8), edge(1, 9)],
  };
}
