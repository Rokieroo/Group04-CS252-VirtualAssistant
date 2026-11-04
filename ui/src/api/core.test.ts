import { describe, expect, it, vi } from "vitest";
import {
  createsRoadmapCycle,
  liveCoreService,
  previewRoadmap,
  uploadError,
  warningsFor,
  type SyllabusDraft,
} from "./core";

const draft: SyllabusDraft = {
  id: "sy_1",
  course_id: "csc10014",
  file_name: "CSC10014.pdf",
  pages: 6,
  raw_text: "CSC10014",
  status: "draft",
  outcomes: [{ code: "CLO1", description: "Learn" }],
  weeks: [{ week: 15, topics: ["Problem framing"] }],
  assessments: [
    { name: "Midterm", weight: 30, due_week: 8 },
    { name: "Final", weight: 60, due_week: 15 },
  ],
  textbooks: [],
  warnings: [],
};
describe("core syllabus and roadmap", () => {
  it("clears the blocking weight warning after correction", () => {
    expect(
      warningsFor(draft).find((w) => w.code === "weights_sum")?.blocking,
    ).toBe(true);
    expect(
      warningsFor({
        ...draft,
        assessments: [
          { ...draft.assessments[0] },
          { ...draft.assessments[1], weight: 70 },
        ],
      }).filter((w) => w.blocking),
    ).toEqual([]);
  });
  it("validates files before any request", () => {
    expect(uploadError({ name: "syllabus.png", size: 10 })).toMatch(/PDF/);
    expect(
      uploadError({ name: "syllabus.pdf", size: 21 * 1024 * 1024 }),
    ).toMatch(/20 MB/);
  });
  it("rejects a prerequisite cycle", () => {
    const edges = [
      {
        parent_id: "a",
        child_id: "b",
        kind: "strict" as const,
        confidence: 1,
        origin: "user" as const,
      },
    ];
    expect(createsRoadmapCycle(edges, "b", "a")).toBe(true);
    expect(createsRoadmapCycle(edges, "b", "c")).toBe(false);
  });
  it("previews a roadmap from the reviewed syllabus before calling the live generator", () => {
    const proposal = previewRoadmap(draft);
    expect(proposal.id).toBe("preview");
    expect(proposal.nodes.map((n) => n.title)).toEqual([
      "Problem framing",
      "Midterm",
      "Final",
    ]);
  });
  it("submits the corrected syllabus fields in the confirmation payload", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "sy_1",
        course_id: "csc10014",
        raw_text: "CSC10014",
        learning_outcomes: [],
        assessments: [],
      }),
    });
    vi.stubGlobal("fetch", fetch);
    try {
      await liveCoreService.confirm({
        ...draft,
        assessments: [
          { ...draft.assessments[0] },
          { ...draft.assessments[1], weight: 70 },
        ],
      });
      expect(fetch).toHaveBeenCalledOnce();
      const request = fetch.mock.calls[0][1] as RequestInit;
      expect(JSON.parse(String(request.body))).toMatchObject({
        assessments: [{ weight: 30 }, { weight: 70 }],
        learning_outcomes: [{ code: "CLO1" }],
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
