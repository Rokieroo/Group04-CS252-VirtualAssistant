import { BackendError } from "../api/backend";
import type { NodeStatus } from "../api/core";
import { syllabusError } from "../api/syllabus";

/**
 * One sentence for any failure. The server's own sentence wins when it sent one;
 * bare codes and network failures get the Vietnamese text of ``syllabusError``.
 */
export function explain(error: unknown): string {
  if (error instanceof BackendError && error.status > 0 && error.status !== 401 && /\s/.test(error.code))
    return error.code;
  return syllabusError(error);
}

/** 90 → "1 giờ 30 phút"; short enough for a chip. */
export function duration(minutes: number | null | undefined): string {
  if (!minutes) return "";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} phút`;
  return rest ? `${hours} giờ ${rest} phút` : `${hours} giờ`;
}

export const statusLabels: Record<NodeStatus, string> = {
  locked: "Chưa mở",
  available: "Sẵn sàng học",
  in_progress: "Đang học",
  done: "Đã xong",
  needs_review: "Cần ôn lại",
};

/** The graph endpoint and the roadmap endpoint name the same states differently. */
export function toStatus(value: string | null | undefined): NodeStatus {
  switch (value) {
    case "done":
    case "mastered":
    case "completed":
      return "done";
    case "in_progress":
      return "in_progress";
    case "needs_review":
    case "review_due":
      return "needs_review";
    case "locked":
      return "locked";
    default:
      return "available";
  }
}

const dayFormat = new Intl.DateTimeFormat("vi-VN", {
  weekday: "long",
  day: "numeric",
  month: "numeric",
});
const timeFormat = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" });

export const dayLabel = (value: string | Date) => {
  const text = dayFormat.format(new Date(value));
  return text.charAt(0).toUpperCase() + text.slice(1);
};
export const timeLabel = (value: string | Date) => timeFormat.format(new Date(value));
export const dateTimeLabel = (value: string | Date) =>
  `${timeLabel(value)}, ${dayLabel(value).toLowerCase()}`;

/** Local "YYYY-MM-DDTHH:mm" for a datetime-local input, ``minutes`` from now. */
export function localAfter(minutes: number, now = Date.now()): string {
  const date = new Date(now + minutes * 60_000);
  date.setSeconds(0, 0);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
