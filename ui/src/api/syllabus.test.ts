import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendError } from "./backend";
import {
  confirmationPayload,
  restoreSavedSyllabus,
  confirmSyllabus,
  normalizeDate,
  syllabusError,
  uploadSyllabus,
  validateDraft,
  type Preview,
} from "./syllabus";
import type { SyllabusDraft } from "./core";
vi.mock("./courses", () => ({
  courseId: vi.fn(async () => "owned-course"),
  currentCourse: { name: "Course" },
}));
const draft: SyllabusDraft = {
  id: "",
  course_id: "owned-course",
  file_name: "CSC10014.pdf",
  pages: 2,
  raw_text: "original source",
  status: "draft",
  course: {
    term_start: { value: "2026-09-01" },
    term_end: { value: "2026-12-31" },
  },
  outcomes: [{ code: "CLO1", description: "Learn", source_page: 1 }],
  weeks: [
    { week: 1, topics: ["Framing"], readings: ["Chapter 1"], source_page: 1 },
    { week: 2, topics: ["Review"], source_page: 2 },
  ],
  assessments: [{ name: "Exam", weight: 90, due_week: 2, source_page: 2 }],
  textbooks: [
    { title: "Book", author: "Author", required: true, source_page: 2 },
  ],
  warnings: [
    {
      code: "weights_sum",
      message: "Old API warning",
      blocking: true,
      path: "assessments",
    },
  ],
  source_pages: { 1: "page one", 2: "page two" },
};
const valid = () => ({
  ...structuredClone(draft),
  assessments: [{ ...draft.assessments[0], weight: 100 }],
});
const preview: Preview = {
  pages: 2,
  status: "draft",
  source_pages: { 1: "page one", 2: "page two" },
  warnings: draft.warnings,
  parsed: {
    course: draft.course!,
    outcomes: [{ code: "CLO1", text: "Learn", source_page: 1 }],
    weeks: draft.weeks,
    assessments: [
      { title: "Exam", weight: 90, due: "21/12/2026", source_page: 2 },
    ],
    textbooks: [
      { title: "Book", authors: "Author", required: true, source_page: 2 },
    ],
  },
};
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
afterEach(() => vi.unstubAllGlobals());
describe("#56 real syllabus adapter", () => {
  it("uploads a syllabus and keeps the page evidence the parse returns", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        reply({ file_name: "CSC10014.pdf", status: "processed" }, 201),
      )
      .mockResolvedValueOnce(reply(preview));
    vi.stubGlobal("fetch", fetch);
    const actual = await uploadSyllabus(new File(["pdf"], "CSC10014.pdf"));
    expect(fetch.mock.calls.map((c) => c[0])).toEqual([
      expect.stringContaining("/courses/owned-course/sources"),
      expect.stringContaining("/syllabus:parse"),
    ]);
    expect((fetch.mock.calls[0][1].body as FormData).get("kind")).toBe(
      "syllabus",
    );
    expect(actual.source_pages).toEqual({ 1: "page one", 2: "page two" });
    expect(actual.assessments[0].due_date).toBe("2026-12-21");
    expect(actual.textbooks[0].author).toBe("Author");
    expect(actual.id).toBe("");
    expect(actual.warnings).toEqual(draft.warnings);
  });
  it("parses pasted text directly without creating a persisted syllabus", async () => {
    const fetch = vi.fn().mockResolvedValue(reply(preview));
    vi.stubGlobal("fetch", fetch);
    const actual = await uploadSyllabus("CSC10014 syllabus");
    expect(fetch).toHaveBeenCalledOnce();
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      text: "CSC10014 syllabus",
    });
    expect(actual.source_pages).toEqual(preview.source_pages);
  });
  it("asks for a draft syllabus when the learner pastes goals instead (#114)", async () => {
    const fetch = vi.fn().mockResolvedValue(reply(preview));
    vi.stubGlobal("fetch", fetch);
    await uploadSyllabus("Recursion\nSorting", { goals: true });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      text: "Recursion\nSorting",
      kind: "goals",
    });
  });
  it("saves the corrected complete draft, including fields without database columns", async () => {
    const fetch = vi.fn().mockResolvedValue(reply({ id: "saved" }));
    vi.stubGlobal("fetch", fetch);
    const d = valid();
    const saved = await confirmSyllabus(d);
    expect(fetch.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(
      confirmationPayload(d),
    );
    expect(confirmationPayload(d).parsed).toMatchObject({
      weeks: d.weeks,
      source_pages: d.source_pages,
      textbooks: [{ authors: "Author", required: true }],
      original_text: "original source",
    });
    expect(saved.status).toBe("confirmed");
    expect(saved.id).toBe("saved");
  });
  it("blocks invalid confirmation without HTTP and updates the same saved draft", async () => {
    const fetch = vi.fn().mockResolvedValue(reply({ id: "saved" }));
    vi.stubGlobal("fetch", fetch);
    await expect(confirmSyllabus(draft)).rejects.toMatchObject({
      code: "has_blocking_warnings",
    });
    expect(fetch).not.toHaveBeenCalled();
    await confirmSyllabus({ ...valid(), id: "saved" });
    expect(fetch.mock.calls[0][0]).toMatch(/syllabus\/saved$/);
    expect(fetch.mock.calls[0][1].method).toBe("PUT");
  });
  it("rejects oversized or unsupported input without HTTP", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      uploadSyllabus(new File(["text"], "bad.png")),
    ).rejects.toMatchObject({ status: 415 });
    await expect(uploadSyllabus("x".repeat(120001))).rejects.toMatchObject({
      status: 422,
    });
    expect(fetch).not.toHaveBeenCalled();
  });
});
describe("#56 warning resolution", () => {
  it("replaces an API weight warning after inline correction", () => {
    expect(
      validateDraft(draft).filter((w) => w.code === "weights_sum"),
    ).toHaveLength(1);
    expect(validateDraft(valid()).filter((w) => w.blocking)).toEqual([]);
  });
  it("keeps unknown blocking warnings and requires explicit review of source problems", () => {
    const d = {
      ...valid(),
      warnings: [
        {
          code: "missing_source",
          message: "Check original",
          blocking: true,
          path: "outcomes.0",
        },
      ],
    };
    expect(validateDraft(d).some((w) => w.blocking)).toBe(true);
    expect(
      validateDraft({
        ...d,
        reviewed_warnings: ["missing_source:outcomes.0"],
      }).some((w) => w.blocking),
    ).toBe(false);
    expect(
      validateDraft({
        ...d,
        warnings: [
          { code: "new_server_check", message: "Unknown", blocking: true },
        ],
        reviewed_warnings: ["new_server_check:"],
      }).some((w) => w.blocking),
    ).toBe(true);
  });
  it("rechecks week ordering, duplicate topics, estimated weeks and assessment dates", () => {
    expect(
      validateDraft({
        ...valid(),
        weeks: [
          { week: 2, topics: ["A"] },
          { week: 1, topics: ["A"] },
        ],
        assessments: [{ name: "Exam", weight: 100, due_week: 3 }],
      }).map((w) => w.code),
    ).toEqual(
      expect.arrayContaining([
        "week_order",
        "duplicate_topic",
        "due_outside_weeks",
      ]),
    );
    expect(
      validateDraft({
        ...valid(),
        weeks: [{ week: 1, topics: ["A"], estimated: true }],
        course: {},
        assessments: [{ name: "Exam", weight: 100, due_week: 1 }],
      }).map((w) => w.code),
    ).toContain("unverified_estimate");
    expect(
      validateDraft({
        ...valid(),
        assessments: [
          { name: "Exam", weight: 100, due_week: null, due_date: "2027-01-01" },
        ],
      }).map((w) => w.code),
    ).toContain("date_outside_term");
  });
  it("normalizes only valid unambiguous dates", () => {
    expect(normalizeDate("21/12/2026")).toBe("2026-12-21");
    expect(normalizeDate("31/02/2026")).toBe("");
  });
  it.each([400, 413, 415, 422, 401, 503, 0])(
    "provides a readable Vietnamese message for HTTP %s",
    (status) => {
      expect(
        syllabusError(new BackendError(status, "internal_code")),
      ).not.toContain("internal_code");
      expect(
        syllabusError(new BackendError(status, "internal_code")).length,
      ).toBeGreaterThan(20);
    },
  );
});

it("restores reviewed syllabus metadata without parsing or losing source evidence", () => {
  const d = valid();
  const parsed = confirmationPayload(d).parsed;
  const restored = restoreSavedSyllabus({
    id: "saved",
    syllabus_id: "saved",
    course_id: "another-course",
    created_at: "2026-11-11T00:00:00Z",
    raw_text: JSON.stringify(parsed),
    learning_outcomes: d.outcomes.map((o) => ({
      ...o,
      id: "outcome-id",
      syllabus_id: "saved",
      bloom_level: "understand",
    })),
    assessments: d.assessments.map((a) => ({
      ...a,
      id: "assessment-id",
      syllabus_id: "saved",
    })),
  });
  expect(restored).toMatchObject({
    id: "saved",
    course_id: "another-course",
    status: "confirmed",
    file_name: d.file_name,
    raw_text: d.raw_text,
    source_pages: d.source_pages,
    weeks: d.weeks,
    textbooks: d.textbooks,
  });
  expect(restored.outcomes[0].source_page).toBe(1);
  expect(restored.assessments[0].source_page).toBe(2);
  expect(validateDraft(restored).some((w) => w.blocking)).toBe(false);
});
it("keeps a legacy plain-text syllabus editable without inventing review fields", () => {
  const result = restoreSavedSyllabus({
    id: "old",
    syllabus_id: "old",
    course_id: "course",
    created_at: "",
    raw_text: "Plain syllabus",
    learning_outcomes: [],
    assessments: [],
  });
  expect(result.raw_text).toBe("Plain syllabus");
  expect(result.weeks).toEqual([]);
  expect(result.source_pages).toEqual({});
  expect(validateDraft(result).some((w) => w.blocking)).toBe(true);
});
