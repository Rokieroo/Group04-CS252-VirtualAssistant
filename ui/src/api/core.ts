import { createsCycle } from "../concepts";
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
  origin: "llm" | "user" | "week_order";
  reason?: string;
};
export type NodeStatus =
  "locked" | "available" | "in_progress" | "done" | "needs_review";
export type RoadmapDraft = {
  id: string;
  course_id?: string;
  nodes: (RoadmapNode & { status?: NodeStatus })[];
  edges: Edge[];
  overloaded_weeks: number[];
};
export type UploadOptions = { goals?: boolean };
export type CoreService = {
  /** ``goals``: pasted goals or a table of contents, from a learner with no syllabus. */
  upload(file: File | string, options?: UploadOptions): Promise<SyllabusDraft>;
  confirm(draft: SyllabusDraft): Promise<SyllabusDraft>;
  generate(syllabusId: string, courseId?: string): Promise<RoadmapDraft>;
  save(roadmap: RoadmapDraft): Promise<RoadmapDraft>;
  schedule(
    roadmapId: string,
    weeklyMinutes: number,
    maxDailyMinutes: number,
  ): Promise<{
    sessions: { id: string; title: string; starts_at: string }[];
    unscheduled?: { task_id: string; reason: string }[];
    overloaded_weeks?: string[];
  }>;
};
export function createsRoadmapCycle(
  edges: Edge[],
  parent: string,
  child: string,
): boolean {
  return createsCycle(edges, parent, child);
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
  async generate(id, selectedCourseId) {
    const r = await call<Roadmap>(
      `/courses/${selectedCourseId ?? (await courseId(currentCourse.name))}/roadmap:generate`,
      {
        method: "POST",
        body: JSON.stringify({ syllabus_id: id }),
      },
    );
    const edges = await call<Edge[]>(`/roadmaps/${r.id}/edges`);
    return {
      id: r.id,
      course_id: r.course_id,
      nodes: r.nodes,
      edges,
      overloaded_weeks: [],
    };
  },
  async save(roadmap) {
    const stored = await call<Edge[]>(`/roadmaps/${roadmap.id}/edges`);
    for (const edge of stored)
      if (
        !roadmap.edges.some(
          (e) => e.parent_id === edge.parent_id && e.child_id === edge.child_id,
        )
      )
        await call(
          `/roadmaps/${roadmap.id}/edges/${edge.parent_id}/${edge.child_id}`,
          { method: "DELETE" },
        );
    for (const edge of roadmap.edges)
      if (
        !stored.some(
          (e) => e.parent_id === edge.parent_id && e.child_id === edge.child_id,
        )
      )
        await call(`/roadmaps/${roadmap.id}/edges`, {
          method: "POST",
          body: JSON.stringify({
            parent_id: edge.parent_id,
            child_id: edge.child_id,
            kind: edge.kind,
            reason: edge.reason || "",
          }),
        });
    return {
      ...roadmap,
      edges: await call<Edge[]>(`/roadmaps/${roadmap.id}/edges`),
    };
  },
  async schedule(id, weekly, daily) {
    const p = await call<{
      tasks: { id: string; title: string }[];
      unscheduled: { task_id: string; reason: string }[];
      overloaded_weeks: string[];
      sessions: { id: string; starts_at: string; task_id: string }[];
    }>(`/roadmaps/${id}:schedule`, {
      method: "POST",
      body: JSON.stringify({
        weekly_minutes: weekly,
        max_daily_minutes: daily,
      }),
    });
    return {
      unscheduled: p.unscheduled,
      overloaded_weeks: p.overloaded_weeks,
      sessions: p.sessions.map((s) => ({
        id: s.id,
        title:
          p.tasks.find((t) => t.id === s.task_id)?.title || "Study session",
        starts_at: s.starts_at,
      })),
    };
  },
};
