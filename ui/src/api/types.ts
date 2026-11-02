/** Proposed learning-check contract. Backend owners must review before deployment. */
export type Citation = { sourceId: string; fileName: string; page: number };
export type Question = {
  id: string;
  prompt: string;
  options: { id: string; text: string }[];
  citations: Citation[];
};
export type LearningCheck = {
  id: string;
  sessionId: string;
  title: string;
  kind: "subject" | "workflow-demo";
  questions: Question[];
};
export type Answer = { questionId: string; optionId: string };
export type CheckResult = {
  checkId: string;
  sessionId: string;
  score: number;
  passed: boolean;
  feedback: string;
  explanations: { questionId: string; text: string }[];
};
export type Submission = { attemptId: string; answers: Answer[] };
export type CheckSession = { id: string; courseId: string };
export interface LearningCheckService {
  load(session: CheckSession, signal?: AbortSignal): Promise<LearningCheck>;
  submit(
    check: LearningCheck,
    submission: Submission,
    signal?: AbortSignal,
  ): Promise<CheckResult>;
}

// Core loop (spec 8). Wire format in snake_case, as docs/openapi.json serves it;
// src/api/contract.test.ts fails when these drift from that file.
export type LearningOutcome = {
  id: string;
  syllabus_id: string;
  code: string;
  description: string;
  bloom_level: string;
};
export type Assessment = {
  id: string;
  syllabus_id: string;
  name: string;
  weight: number;
  due_week: number | null;
};
/** GET/POST/PUT /courses/{id}/syllabus (spec 8.1–8.2). */
export type Syllabus = {
  id: string;
  syllabus_id: string;
  course_id: string;
  raw_text: string;
  created_at: string;
  learning_outcomes: LearningOutcome[];
  assessments: Assessment[];
};
/** One step of a roadmap; a milestone ``covers`` the topic node ids it tests. */
export type RoadmapNode = {
  id: string;
  roadmap_id: string;
  type: "topic" | "milestone";
  kind: "topic" | "milestone" | null;
  title: string;
  week: number | null;
  duration_minutes: number | null;
  est_minutes: number | null;
  due_at: string | null;
  covers: string[];
};
/** POST /courses/{id}/roadmap:generate and GET /roadmaps/{id} (spec 8.3). */
export type Roadmap = {
  id: string;
  roadmap_id: string;
  course_id: string;
  user_id: string;
  title: string;
  created_at: string;
  nodes: RoadmapNode[];
};
/** A web source chosen for a node (spec 8.6); the backend does not serve it yet. */
export type Resource = {
  id: string;
  rank: number;
  title: string;
  url: string;
  domain: string;
  format: "article" | "video" | "course" | "book" | "paper" | "exercise";
  language: string;
  duration_min: number | null;
  is_free: boolean;
  score: number;
  breakdown: Record<
    | "relevance"
    | "authority"
    | "level_fit"
    | "pedagogy"
    | "freshness"
    | "accessibility"
    | "community",
    number
  >;
  reason: string;
  evidence_quote: string;
  pinned: boolean;
};
/** GET /roadmap-nodes/{id}/resources (spec 8.6). */
export type NodeResources = {
  status: "searching" | "ready" | "insufficient";
  resources: Resource[];
  gaps: string[];
};
