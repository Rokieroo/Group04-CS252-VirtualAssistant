/** The real workspace API. Session credentials stay in this tab's sessionStorage. */
// Wire types of the planner endpoints (docs/openapi.json); requests go through api/backend `call`.
export type User = {
  id: string; name: string; email: string; timezone: string; personality: string;
  role: string; account_level: "university" | "k12"; birth_year: number | null;
  companion_mode: "off" | "buddy" | "mentor" | "girlfriend";
};
export type Auth = { access_token: string; expires_at: string; user: User };
export type Goal = { id: string; title: string; description: string; due_at: string | null };
export type Task = {
  id: string; owner_id: string; assignee_id: string; goal_id: string | null; team_id: string | null;
  title: string; description: string; duration_minutes: number; completed_minutes: number;
  priority: number; due_at: string; status: string;
};
export type Window = { id: string; starts_at: string; ends_at: string };
export type BusyBlock = Window & { title: string };
export type Entry = Window & { task_id: string; status: string; actual_minutes: number };
export type ProposedEntry = Omit<Entry, "id" | "status" | "actual_minutes">;
export type Plan = {
  committed: boolean; expired_sessions: number; entries: ProposedEntry[];
  unscheduled: { task_id: string; minutes: number; reason: string }[];
};
export type PlanRequest = {
  starts_at: string; ends_at: string; max_session_minutes: number; daily_limit_minutes: number;
};
export type Team = { id: string; name: string; owner_id: string };
export type Member = { id: string; name: string };
export type Invitation = { id: string; team_id: string; team_name: string; email: string; accepted: boolean };
export type Notification = { id: string; message: string; read: boolean; entry_id: string | null };
export type Report = {
  total_tasks: number; completed_tasks: number; planned_minutes: number; completed_minutes: number;
  missed_sessions: number; completion_percent: number; start_date: string; end_date: string;
};
export type Message = { id: string; role: "user" | "assistant"; content: string };
export type ChatReply = { reply: string; provider: "llm" | "offline"; fallback_reason: string | null };
