import { uploadSyllabus, confirmSyllabus } from "./syllabus";
import { courseId, currentCourse } from "./courses";
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
export const liveCoreService: CoreService = {
  upload: uploadSyllabus,
  confirm: confirmSyllabus,
  async generate(id) {
    const r = await call<Roadmap>(
      `/courses/${await courseId(currentCourse.name)}/roadmap:generate`,
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
