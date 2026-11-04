// Old — retained for legacy demo/reference; not used by the redesigned course journey.
export type Course = {
  id: string;
  name: string;
  category: string;
  description: string;
  prerequisite: string;
  weeks: number;
  level: string;
  color: string;
  topics: string[];
};
export type Session = {
  id: string;
  courseId: string;
  title: string;
  date: string;
  time: string;
  minutes: number;
  kind: "lesson" | "quiz";
  status: "planned" | "studied" | "verified";
};
export type State = {
  version: 2;
  scheduleDate: string;
  active: string[];
  future: string[];
  sessions: Session[];
  verified: string[];
  name: string;
  hours: number;
  messages: { role: "user" | "assistant"; text: string }[];
};
/** A scripted plan change the demo assistant offers for approval. */
export type Proposal = {
  kind: "enroll" | "balance";
  courseId?: string;
  stage: "check" | "review";
  hours: number;
};
