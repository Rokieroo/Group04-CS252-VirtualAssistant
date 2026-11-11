import { parseSyllabusText, readPages } from "./demoParser";
import { checkSyllabusInput, validateDraft } from "./syllabus";
import type { CoreService, Edge, NodeStatus, RoadmapDraft, SyllabusDraft } from "./core";
import type { RoadmapNode } from "./types";

// The labelled UI preview (no backend). Uploads are parsed in the browser by demoParser;
// this CSC10014 sample is only the roadmap shown before anything is uploaded.
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
  async upload(file, options) {
    checkSyllabusInput(file);
    const fileName = typeof file === "string" ? "Nội dung đã dán" : file.name;
    if (options?.goals && typeof file === "string") return goalsDraft(file);
    return parseSyllabusText(await readPages(file), fileName);
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
    return roadmapFrom(mockConfirmed);
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

/** Pasted learning goals, one per line, become one week each (the server drafts these with its LLM). */
function goalsDraft(text: string): SyllabusDraft {
  const goals = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).slice(0, 52);
  return {
    ...cloneFixture(),
    id: "sy_goals",
    file_name: "Mục tiêu học tập",
    pages: 1,
    raw_text: text,
    outcomes: [],
    assessments: [],
    textbooks: [],
    weeks: goals.map((goal, i) => ({ week: i + 1, topics: [goal], source_page: 1 })),
    source_pages: { 1: text.slice(0, 4000) },
  };
}

/**
 * The server builder's rules without its LLM (app/roadmap/builder.py, nodes.py): one node
 * per topic and assessment, a soft edge from the last topic of a week to the first of the
 * next, and a milestone covering every topic up to its week. Strict prerequisites come
 * from the LLM in the full app, so the preview proposes none.
 */
export function roadmapFrom(syllabus: SyllabusDraft): RoadmapDraft {
  const id = "rm_preview";
  const lastWeek = Math.max(1, ...syllabus.weeks.map((w) => w.week));
  const topics = syllabus.weeks.flatMap((w) =>
    w.topics.map((title) => ({ title, week: w.week })),
  );
  const nodes: (RoadmapNode & { status?: NodeStatus })[] = topics.map((t, i) => ({
    id: `n_${i + 1}`,
    roadmap_id: id,
    title: t.title,
    week: t.week,
    type: "topic",
    kind: "topic",
    duration_minutes: 90,
    est_minutes: 90,
    due_at: null,
    covers: [],
  }));
  syllabus.assessments.forEach((a, i) => {
    const week = a.due_week ?? lastWeek;
    nodes.push({
      id: `m_${i + 1}`,
      roadmap_id: id,
      title: a.name,
      week,
      type: "milestone",
      kind: "milestone",
      duration_minutes: 30,
      est_minutes: 30,
      due_at: null,
      covers: nodes.filter((n) => n.type === "topic" && (n.week ?? 1) <= week).map((n) => n.id),
    });
  });
  const weeks = [...new Set(topics.map((t) => t.week))];
  const edges: Edge[] = weeks.slice(1).map((week, i) => {
    const earlier = nodes.filter((n) => n.type === "topic" && n.week === weeks[i]);
    return {
      parent_id: earlier[earlier.length - 1].id,
      child_id: nodes.find((n) => n.type === "topic" && n.week === week)!.id,
      kind: "soft",
      confidence: 1,
      origin: "week_order",
      reason: `week ${weeks[i]} -> week ${week}`,
    };
  });
  return { id, nodes, edges, overloaded_weeks: [] };
}
