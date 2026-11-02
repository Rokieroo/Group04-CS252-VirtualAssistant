import { checkFile, type Concept, type Graph, type Prereq } from "../concepts";
import { BackendError, call, session } from "./backend";

// Spec 8.1–8.2 on the real backend. The demo's stand-in is demo/courses.ts.
export type UploadResult = {
  file_name: string;
  pages: number;
  status: "processing" | "processed" | "error";
  warning?: "scanned_pdf";
};
type Code =
  | "not_pdf"
  | "unsupported_type"
  | "file_too_large"
  | "invalid_pdf"
  | "invalid_file"
  | "scanned_pdf"
  | "concepts_unavailable"
  | "items_unavailable"
  | "upload_in_progress";
const CODES: readonly string[] = [
  "not_pdf",
  "unsupported_type",
  "file_too_large",
  "invalid_pdf",
  "invalid_file",
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

/** What the course materials page needs; the backend and the demo each provide one. */
export interface CourseService {
  /** True when every file is extracted and concepts are stored, so questions can be written. */
  readonly live: boolean;
  uploadSource(course: string, file: File): Promise<UploadResult>;
  /** Concepts of the whole course after extracting ``fileName``. */
  proposeConcepts(course: string, fileName: string): Promise<Graph>;
  /** Writes new questions for a stored concept and returns all of its questions. */
  generateItems(course: string, conceptId: string): Promise<Item[]>;
}

// shortcut: one fixed course until the course list (S2) lets the user pick one.
export const currentCourse = {
  id: "csc10014",
  name: "CS252 - Computational Thinking",
};

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
  const form = new FormData();
  form.append("file", file);
  // Slow on purpose: the vision model reads the slides before this returns.
  const result = await backend<UploadResult>(`/courses/${await courseId(course)}/sources`, {
    method: "POST",
    body: form,
  });
  return { ...result, warning: result.warning ?? undefined };
}

export async function proposeConcepts(course: string, fileName: string): Promise<Graph> {
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

export const backendCourses: CourseService = {
  live: true,
  uploadSource,
  proposeConcepts,
  generateItems,
};
