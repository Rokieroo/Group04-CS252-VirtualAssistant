/** The real workspace API. Session credentials stay in this tab's sessionStorage. */
import { API_ORIGIN, errorDetail } from "./api/backend";

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

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export class ApiClient {
  constructor(
    private token = "",
    private onUnauthorized: () => void = () => {},
    private baseUrl = API_ORIGIN,
  ) {}

  async request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30_000);
    try {
      const response = await fetch(this.baseUrl.replace(/\/$/, "") + path, {
        method, signal: controller.signal,
        headers: {
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (!response.ok) {
        if (response.status === 401 && this.token) this.onUnauthorized();
        throw new ApiError(response.status, await errorDetail(response));
      }
      if (response.status === 204) return undefined as T;
      return await response.json() as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new Error(error instanceof Error && error.name === "AbortError"
        ? "The request timed out. Please try again."
        : "Cannot reach the workspace. Start the backend and check your connection.");
    } finally {
      clearTimeout(timer);
    }
  }
}
