import { BackendError, call } from "./backend";
import { courseId, currentCourse } from "./courses";
import type { SyllabusDraft, Warning } from "./core";
import type { Syllabus } from "./types";

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_TEXT_CHARS = 120000;
type Parsed = {
  course: NonNullable<SyllabusDraft["course"]>;
  outcomes: {
    code: string;
    text: string;
    bloom_level?: string;
    source_page?: number;
  }[];
  weeks: SyllabusDraft["weeks"];
  assessments: {
    title: string;
    weight?: number;
    due?: string;
    kind?: string;
    source_page?: number;
  }[];
  textbooks: {
    title: string;
    authors?: string;
    required?: boolean;
    source_page?: number;
  }[];
};
export type Preview = {
  parsed: Parsed;
  warnings: Warning[];
  pages: number;
  file_name?: string;
  status: string;
  source_pages: Record<number, string>;
};
export const warningKey = (w: Warning) => `${w.code}:${w.path || ""}`;
/** Warnings the learner clears by ticking that they checked the source page. */
export const manuallyReviewable = new Set([
  "missing_source",
  "ungrounded_field",
]);
const recalculated = new Set([
  "weights_sum",
  "week_order",
  "weeks_order",
  "missing_due",
  "due_outside_weeks",
  "date_outside_term",
  "term_order",
  "duplicate_topic",
  "empty_week",
  "missing_weeks",
  "missing_assessments",
  "unknown_term",
  "unverified_estimate",
]);
export function validateDraft(d: SyllabusDraft): Warning[] {
  const result = d.warnings.filter(
    (w) =>
      !recalculated.has(w.code) &&
      !(
        manuallyReviewable.has(w.code) &&
        d.reviewed_warnings?.includes(warningKey(w))
      ),
  );
  const add = (code: string, message: string, path = "", blocking = true) =>
    result.push({ code, message, path, blocking });
  if (!d.weeks.length)
    add("weeks_empty", "Add at least one study week.", "weeks");
  const weeks = d.weeks.map((w) => w.week);
  if (
    weeks.some(
      (w, i) =>
        !Number.isInteger(w) || w < 1 || w > 52 || (i > 0 && w <= weeks[i - 1]),
    )
  )
    add(
      "week_order",
      "Weeks must be strictly increasing, unique, and between 1 and 52.",
      "weeks",
    );
  const maxWeek = Math.max(0, ...weeks.filter(Number.isFinite));
  if (
    maxWeek <= 52 &&
    Array.from({ length: maxWeek }, (_, i) => i + 1).some(
      (w) => !weeks.includes(w),
    )
  )
    add("missing_weeks", "There are missing weeks in the schedule.", "weeks", false);
  if (!d.assessments.length)
    add(
      "missing_assessments",
      "No assessments found; please check the syllabus.",
      "assessments",
      false,
    );
  const seen = new Map<string, number>();
  d.weeks.forEach((w, i) => {
    if (!w.topics.some((t) => t.trim()))
      add("empty_week", "Each week needs at least one topic.", `weeks.${i}`);
    for (const t of w.topics.filter((t) => t.trim())) {
      const k = t.trim().toLocaleLowerCase();
      if (seen.has(k) && seen.get(k) !== w.week)
        add("duplicate_topic", `Topic ${t} appears in multiple weeks.`, `weeks.${i}`);
      seen.set(k, w.week);
    }
  });
  d.outcomes.forEach((o, i) => {
    if (!o.code.trim() || !o.description.trim())
      add(
        "outcome_empty",
        "Enter both code and description for the learning outcome.",
        `outcomes.${i}`,
      );
  });
  d.textbooks.forEach((b, i) => {
    if (!b.title.trim())
      add("book_empty", "Enter the textbook title.", `textbooks.${i}`);
  });
  if (d.assessments.length) {
    const sum = d.assessments.reduce((n, a) => n + a.weight, 0);
    if (
      !Number.isFinite(sum) ||
      Math.abs(sum - 100) > 1 + 1e-9 ||
      d.assessments.some((a) => a.weight < 0 || a.weight > 100)
    )
      add(
        "weights_sum",
        `Total weight is ${sum}%; expected 100% ± 1.`,
        "assessments",
      );
  }
  const start = String(d.course?.term_start?.value || ""),
    end = String(d.course?.term_end?.value || "");
  if (start && end && start > end)
    add("term_order", "Start date must be before end date.", "course");
  d.weeks.forEach((w, i) => {
    if (
      w.estimated &&
      (!start ||
        !end ||
        start > end ||
        w.week >
          Math.ceil(
            (Date.parse(end) - Date.parse(start) + 86400000) / 604800000,
          ))
    )
      add(
        "unverified_estimate",
        "Term dates are incomplete to verify estimated weeks.",
        "weeks." + i,
      );
  });
  d.assessments.forEach((a, i) => {
    const path = `assessments.${i}`;
    if (!a.name.trim()) add("assessment_empty", "Enter the assessment name.", path);
    if (!a.due_week && !a.due_date)
      add("missing_due", "Milestones need a due week or due date.", path);
    if (
      a.due_week !== null &&
      (!Number.isInteger(a.due_week) ||
        a.due_week < 1 ||
        a.due_week > 52 ||
        (maxWeek > 0 && a.due_week > maxWeek))
    )
      add(
        "due_outside_weeks",
        "Assessment week must fall within the course schedule (1–52).",
        path,
      );
    if (a.due_date && (!start || !end))
      add("unknown_term", "Term dates are incomplete to check the due date.", path, false);
    if (a.due_date && !normalizeDate(a.due_date))
      add("invalid_due_date", "Invalid due date.", path);
    if (
      a.due_date &&
      ((start && a.due_date < start) || (end && a.due_date > end))
    )
      add("date_outside_term", "Assessment date falls outside the term.", path);
  });
  return result;
}
export function normalizeDate(value: string): string {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const local = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(value);
  const iso = parts
    ? value
    : local
      ? local[3] +
        "-" +
        local[2].padStart(2, "0") +
        "-" +
        local[1].padStart(2, "0")
      : "";
  const time = Date.parse(iso);
  return Number.isFinite(time) &&
    new Date(time).toISOString().slice(0, 10) === iso
    ? iso
    : "";
}
/** Rejects input the backend would refuse, so mock and live uploads fail alike. */
export function checkSyllabusInput(input: File | string): void {
  if (
    typeof input === "string"
      ? !input.trim() || input.length > MAX_TEXT_CHARS
      : input.size === 0
  )
    throw new BackendError(422, "invalid_text");
  if (typeof input === "string") return;
  if (input.size > MAX_FILE_BYTES)
    throw new BackendError(413, "file_too_large");
  if (!/\.(pdf|docx)$/i.test(input.name))
    throw new BackendError(415, "unsupported_type");
}
export async function uploadSyllabus(
  input: File | string,
  {
    goals = false,
    courseId: selectedCourseId,
  }: { goals?: boolean; courseId?: string } = {},
): Promise<SyllabusDraft> {
  checkSyllabusInput(input);
  const id = selectedCourseId || (await courseId(currentCourse.name));
  let file_name = "Pasted content";
  if (typeof input !== "string") {
    const body = new FormData();
    body.append("file", input);
    body.append("kind", "syllabus");
    ({ file_name } = await call<{ file_name: string }>(
      `/courses/${id}/sources`,
      { method: "POST", body },
    ));
  }
  const request =
    typeof input === "string"
      ? { text: input, ...(goals ? { kind: "goals" } : {}) }
      : { file_name };
  const result = await call<Preview>(`/courses/${id}/syllabus:parse`, {
    method: "POST",
    body: JSON.stringify(request),
  });
  const { source_pages } = result;
  const p = result.parsed;
  return {
    id: "",
    course_id: id,
    course: p.course,
    raw_text: Object.values(source_pages).join("\n\n"),
    file_name,
    pages: result.pages,
    status: "draft",
    warnings: result.warnings,
    source_pages,
    outcomes: p.outcomes.map((o) => ({ ...o, description: o.text })),
    weeks: p.weeks,
    assessments: p.assessments.map((a) => ({
      name: a.title,
      weight: a.weight ?? 0,
      due_week: a.due?.match(/^(?:week|tuần)\s*(\d+)$/i)
        ? Number(a.due.match(/\d+/)![0])
        : null,
      due_date:
        a.due && !/^(week|tuần)/i.test(a.due)
          ? normalizeDate(a.due) || a.due
          : "",
      kind: a.kind,
      source_page: a.source_page,
    })),
    textbooks: p.textbooks.map((b) => ({
      title: b.title,
      author: b.authors ?? "",
      required: b.required,
      source_page: b.source_page,
    })),
  };
}
export function confirmationPayload(d: SyllabusDraft) {
  // SyllabusIn.parsed is serialized by the existing API into raw_text, retaining
  // fields without dedicated database columns and their original evidence.
  return {
    parsed: {
      course: d.course ?? {},
      outcomes: d.outcomes.map((o) => ({ ...o, text: o.description })),
      weeks: d.weeks,
      assessments: d.assessments.map((a) => ({
        ...a,
        title: a.name,
        due: a.due_date || (a.due_week ? `week ${a.due_week}` : null),
      })),
      textbooks: d.textbooks.map((b) => ({ ...b, authors: b.author })),
      original_text: d.raw_text,
      source_pages: d.source_pages,
      file_name: d.file_name,
      reviewed_warnings: d.reviewed_warnings ?? [],
    },
    learning_outcomes: d.outcomes,
    assessments: d.assessments,
  };
}
export async function confirmSyllabus(
  d: SyllabusDraft,
): Promise<SyllabusDraft> {
  if (validateDraft(d).some((w) => w.blocking))
    throw new BackendError(422, "has_blocking_warnings");
  const id = d.course_id ?? (await courseId(currentCourse.name));
  const saved = await call<Syllabus>(
    `/courses/${id}/syllabus${d.id ? `/${encodeURIComponent(d.id)}` : ""}`,
    {
      method: d.id ? "PUT" : "POST",
      body: JSON.stringify(confirmationPayload(d)),
    },
  );
  return { ...d, id: saved.id, course_id: id, status: "confirmed" };
}
export function syllabusError(error: unknown): string {
  if (!(error instanceof BackendError))
    return error instanceof Error
      ? error.message
      : "Something went wrong. Please try again.";
  const codes: Record<string, string> = {
    not_a_syllabus:
      "This does not look like a syllabus. Choose the right document or paste syllabus text.",
    invalid_text: "Text must be between 1 and 120,000 characters.",
    has_blocking_warnings: "Resolve blocking warnings before confirming.",
    scanned_pdf: "Scanned image PDFs are not supported yet. Paste the syllabus text instead.",
    llm_unavailable: "The parsing service is busy. Please try again.",
    invalid_llm_response: "The parsing result was invalid. Please try again.",
  };
  return (
    codes[error.code] ??
    (
      {
        0: "Could not connect to the server. Check your connection and try again.",
        400: "The file is invalid or corrupted. Please choose another file.",
        401: "Your session has expired. Please sign in again.",
        403: "You do not have permission to access this course.",
        404: "Course or source page not found. Please reload.",
        409: "The file is currently being processed. Wait a moment and try again.",
        413: "File exceeds 20 MB. Compress or split the file first.",
        415: "Only PDF or DOCX files are supported.",
        422: "Invalid content. Check your syllabus and try again.",
        502: "The parsing result was invalid. Please try again.",
        503: "The service is temporarily busy. Please try again.",
      } as Record<number, string>
    )[error.status] ??
    "Could not process your request. Please try again."
  );
}

/** Reopen the reviewed data saved by confirmationPayload; never re-run the parser. */
export function restoreSavedSyllabus(saved: Syllabus): SyllabusDraft {
  let parsed: Partial<ReturnType<typeof confirmationPayload>["parsed"]> = {};
  try {
    const value = JSON.parse(saved.raw_text);
    if (value && !Array.isArray(value) && typeof value === "object")
      parsed = value;
  } catch {
    /* Older syllabuses store plain text without review metadata. */
  }
  const source_pages = parsed.source_pages || {};
  return {
    id: saved.id,
    course_id: saved.course_id,
    status: "confirmed",
    raw_text: parsed.original_text ?? saved.raw_text,
    file_name: parsed.file_name || "Saved syllabus",
    pages: Math.max(
      0,
      ...Object.keys(source_pages).map(Number).filter(Number.isFinite),
    ),
    course: parsed.course || {},
    source_pages,
    reviewed_warnings: parsed.reviewed_warnings || [],
    warnings: [],
    outcomes: saved.learning_outcomes.map((o) => ({
      ...o,
      source_page: parsed.outcomes?.find((p) => p.code === o.code)?.source_page,
    })),
    weeks: parsed.weeks || [],
    assessments: saved.assessments.map((a) => ({
      ...parsed.assessments?.find((p) => p.name === a.name),
      ...a,
    })),
    textbooks: (parsed.textbooks || []).map((b) => ({
      ...b,
      author: b.author ?? b.authors ?? "",
    })),
  };
}
export async function fetchSavedSyllabus(courseId: string) {
  return restoreSavedSyllabus(
    await call<Syllabus>(`/courses/${encodeURIComponent(courseId)}/syllabus`),
  );
}
