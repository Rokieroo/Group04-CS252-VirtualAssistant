import { uploadSyllabus, confirmSyllabus, validateDraft } from "./syllabus";
import { courseId } from "./courses";
import { call } from "./backend";
import type { Roadmap, RoadmapNode } from "./types";

export type Week = {
  week: number;
  topics: string[];
  readings?: string[];
  estimated?: boolean;
  source_page?: number;
};
export type Book = {
  title: string;
  author: string;
  required?: boolean;
  source_page?: number;
};
export type Outcome = {
  code: string;
  description: string;
  bloom_level?: string;
  source_page?: number;
};
export type AssessmentRow = {
  name: string;
  weight: number;
  due_week: number | null;
  due_date?: string;
  kind?: string;
  source_page?: number;
};
export type Warning = {
  code: string;
  message: string;
  blocking: boolean;
  path?: string;
};
export type SyllabusDraft = {
  id: string;
  course_id?: string;
  course?: Record<string, { value: string | number; source_page?: number }>;
  reviewed_warnings?: string[];
  raw_text: string;
  file_name: string;
  pages: number;
  outcomes: Outcome[];
  weeks: Week[];
  assessments: AssessmentRow[];
  textbooks: Book[];
  warnings: Warning[];
  status: "draft" | "confirmed";
  source_pages?: Record<number, string>;
};
export type Edge = {
  parent_id: string;
  child_id: string;
  kind: "strict" | "soft";
  confidence: number;
  origin: "llm" | "user";
};
export type NodeStatus =
  "locked" | "available" | "in_progress" | "done" | "needs_review";
export type RoadmapDraft = {
  id: string;
  nodes: (RoadmapNode & { status?: NodeStatus })[];
  edges: Edge[];
  overloaded_weeks: number[];
};
export type CoreService = {
  upload(file: File | string): Promise<SyllabusDraft>;
  confirm(draft: SyllabusDraft): Promise<SyllabusDraft>;
  generate(syllabusId: string): Promise<RoadmapDraft>;
  schedule(
    roadmapId: string,
    weeklyMinutes: number,
    maxDailyMinutes: number,
  ): Promise<{ sessions: { id: string; title: string; starts_at: string }[] }>;
};
export const MAX_SIZE = 20 * 1024 * 1024;
export function uploadError(file: Pick<File, "name" | "size">): string | null {
  if (file.size > MAX_SIZE)
    return "File lớn hơn 20 MB. Hãy nén hoặc chia nhỏ file.";
  if (!/\.(pdf|docx)$/i.test(file.name)) return "Chỉ hỗ trợ PDF hoặc DOCX.";
  return null;
}
export function warningsFor(draft: SyllabusDraft): Warning[] {
  return validateDraft(draft);
}

export function createsRoadmapCycle(
  edges: Edge[],
  parent: string,
  child: string,
): boolean {
  const stack = [child];
  const visited = new Set<string>();
  while (stack.length) {
    const current = stack.pop()!;
    if (current === parent) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    edges
      .filter((e) => e.parent_id === current)
      .forEach((e) => stack.push(e.child_id));
  }
  return false;
}
/** The live API persists on generate, so show a local proposal until the learner approves. */
export function previewRoadmap(draft: SyllabusDraft): RoadmapDraft {
  const topics = draft.weeks.length
    ? draft.weeks.flatMap((w) =>
        w.topics
          .filter(Boolean)
          .map((title) => ({ title, week: w.week, type: "topic" as const })),
      )
    : draft.outcomes.map((o, index) => ({
        title: o.description,
        week: index + 1,
        type: "topic" as const,
      }));
  const milestones = draft.assessments.map((a) => ({
    title: a.name,
    week: a.due_week ?? 1,
    type: "milestone" as const,
  }));
  const nodes: RoadmapNode[] = [...topics, ...milestones].map(
    (item, index) => ({
      id: `preview-${index}`,
      roadmap_id: "preview",
      type: item.type,
      kind: item.type,
      title: item.title,
      week: item.week,
      duration_minutes: item.type === "topic" ? 90 : 30,
      est_minutes: item.type === "topic" ? 90 : 30,
      due_at: null,
      covers: [],
    }),
  );
  return { id: "preview", nodes, edges: [], overloaded_weeks: [] };
}
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
    await new Promise((resolve) => setTimeout(resolve, 400));
    return {
      ...cloneFixture(),
      file_name: typeof file === "string" ? "Nội dung đã dán" : file.name,
      raw_text: typeof file === "string" ? file : fixture.raw_text,
    };
  },
  async confirm(draft) {
    const warnings = warningsFor(draft);
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
export const liveCoreService: CoreService = {
  upload: uploadSyllabus,
  confirm: confirmSyllabus,
  async generate(id) {
    const r = await call<Roadmap>(
      `/courses/${await courseId("CSC10014 · Introduction to Virtual Assistants")}/roadmap:generate`,
      {
        method: "POST",
        body: JSON.stringify({ syllabus_id: id }),
      },
    );
    return { id: r.id, nodes: r.nodes, edges: [], overloaded_weeks: [] };
  },
  async schedule(id, weekly, daily) {
    const p = await call<{
      sessions: { id: string; starts_at: string; task_id: string }[];
    }>(`/roadmaps/${id}:schedule`, {
      method: "POST",
      body: JSON.stringify({
        weekly_minutes: weekly,
        max_daily_minutes: daily,
      }),
    });
    return {
      sessions: p.sessions.map((s) => ({
        id: s.id,
        title: s.task_id,
        starts_at: s.starts_at,
      })),
    };
  },
};
