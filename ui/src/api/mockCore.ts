import { checkSyllabusInput, validateDraft } from "./syllabus";
import type { CoreService, NodeStatus, SyllabusDraft } from "./core";
import type { RoadmapNode } from "./types";

// The labelled UI preview (no backend): a fixed CSC10014 syllabus stands in for parsing.
const fixture: SyllabusDraft = {
  id: "sy_csc10014",
  file_name: "CSC10014_syllabus.pdf",
  pages: 6,
  raw_text:
    "CSC10014 · Nhập môn trợ lý ảo\nTuần 1: Problem framing, Solution ladder\nTuần 2: Retrieval\nGiữa kỳ: tuần 8 (30%)\nCuối kỳ: tuần 15 (70%)",
  status: "draft",
  warnings: [],
  outcomes: [
    {
      code: "CLO1",
      description: "Phát biểu bài toán và chọn bậc giải pháp phù hợp",
      source_page: 2,
    },
    {
      code: "CLO2",
      description: "Đánh giá nguồn học và kết quả của trợ lý",
      source_page: 2,
    },
  ],
  weeks: [
    { week: 1, topics: ["Problem framing", "Solution ladder"], source_page: 3 },
    { week: 2, topics: ["Retrieval"], source_page: 4 },
    { week: 8, topics: ["Midterm review"], source_page: 5 },
    { week: 15, topics: ["Final review"], source_page: 5 },
  ],
  assessments: [
    { name: "Giữa kỳ", weight: 30, due_week: 8, source_page: 5 },
    { name: "Cuối kỳ", weight: 70, due_week: 15, source_page: 5 },
  ],
  textbooks: [
    { title: "Tài liệu môn CSC10014", author: "Giảng viên", source_page: 6 },
  ],
  source_pages: {
    2: "CLO1: Phát biểu bài toán và chọn bậc giải pháp phù hợp. CLO2: Đánh giá nguồn học và kết quả của trợ lý.",
    3: "Tuần 1: Problem framing; Solution ladder.",
    4: "Tuần 2: Retrieval.",
    5: "Giữa kỳ: 30%, tuần 8. Cuối kỳ: 70%, tuần 15.",
    6: "Giáo trình: Tài liệu môn CSC10014.",
  },
};
const cloneFixture = () => structuredClone(fixture);
let mockConfirmed = cloneFixture();
export const mockCoreService: CoreService = {
  async upload(file) {
    checkSyllabusInput(file);
    await new Promise((resolve) => setTimeout(resolve, 400));
    return {
      ...cloneFixture(),
      file_name: typeof file === "string" ? "Nội dung đã dán" : file.name,
      raw_text: typeof file === "string" ? file : fixture.raw_text,
    };
  },
  async confirm(draft) {
    const warnings = validateDraft(draft);
    if (warnings.some((w) => w.blocking))
      throw new Error(warnings.map((w) => w.message).join(" "));
    mockConfirmed = {
      ...structuredClone(draft),
      warnings,
      status: "confirmed",
    };
    return mockConfirmed;
  },
  async generate() {
    const titles: {
      title: string;
      week: number;
      type: "topic" | "milestone";
    }[] = [
      ...mockConfirmed.weeks.flatMap((w) =>
        w.topics.map((title) => ({
          title,
          week: w.week,
          type: "topic" as const,
        })),
      ),
      ...mockConfirmed.assessments.map((a) => ({
        title: a.name,
        week: a.due_week ?? 1,
        type: "milestone" as const,
      })),
    ];
    const nodes: (RoadmapNode & { status?: NodeStatus })[] = titles.map(
      (x, i) => ({
        id: `n_${i + 1}`,
        roadmap_id: "rm_csc10014",
        title: x.title,
        week: x.week,
        type: x.type,
        kind: x.type,
        duration_minutes: x.type === "topic" ? 90 : 30,
        est_minutes: x.type === "topic" ? 90 : 30,
        due_at: null,
        covers: [],
        status: (
          [
            "done",
            "in_progress",
            "available",
            "needs_review",
            "locked",
          ] as NodeStatus[]
        )[i % 5],
      }),
    );
    return {
      id: "rm_csc10014",
      nodes,
      edges:
        nodes.length > 1
          ? [
              {
                parent_id: nodes[0].id,
                child_id: nodes[1].id,
                kind: "strict",
                confidence: 0.82,
                origin: "llm",
              },
            ]
          : [],
      overloaded_weeks: [],
    };
  },
  async save(roadmap) { return structuredClone(roadmap); },
  async schedule() {
    return {
      sessions: [
        {
          id: "session_1",
          title: "Problem framing",
          starts_at: "2026-11-05T09:00:00+07:00",
        },
      ],
    };
  },
};
