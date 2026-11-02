import { courses, initialState } from "./demo/fixtures";
import type { Session, State } from "./domain";
import { addDays, dateKey, today } from "./time";
export { courses, initialState } from "./demo/fixtures";
export type { Course, Session, State } from "./domain";
export { addDays, dateKey, today } from "./time";

export function enroll(s: State, id: string, hours = 3): State {
  if (s.active.includes(id)) return s;
  const course = courses.find((c) => c.id === id);
  if (!course) return s;
  return {
    ...s,
    active: [...s.active, id],
    future: s.future.filter((x) => x !== id),
    sessions: [
      ...s.sessions,
      ...course.topics.map((title, i) => ({
        id: `${id}-${i}`,
        courseId: id,
        title,
        date: dateKey(addDays(today(), i + 1)),
        time: "16:00",
        minutes: Math.max(10, Math.min(60, Math.floor((hours * 60) / 3))),
        kind: "lesson" as const,
        status: "planned" as const,
      })),
    ],
  };
}
export function saveFuture(s: State, id: string): State {
  return s.active.includes(id) || s.future.includes(id)
    ? s
    : { ...s, future: [...s.future, id] };
}
export function verify(s: State, id: string, score: number): State {
  if (
    score < 70 ||
    s.verified.includes(id) ||
    !s.sessions.some((x) => x.id === id)
  )
    return s;
  return {
    ...s,
    verified: [...s.verified, id],
    sessions: s.sessions.map((x) =>
      x.id === id ? { ...x, status: "verified" } : x,
    ),
  };
}
export function completion(s: State, id: string) {
  const sessions = s.sessions.filter((session) => session.courseId === id);
  const verifiedSessions = sessions.filter((session) =>
    s.verified.includes(session.id),
  ).length;
  // The English demo begins with six completed lessons that have no session records.
  const baseline = id === "english" ? 6 : 0;
  const total = baseline + sessions.length;
  const verified = baseline + verifiedSessions;
  return {
    verified,
    total,
    percent: total ? Math.floor((verified / total) * 100) : 0,
    baseline,
  };
}

export function progress(s: State, id: string) {
  return completion(s, id).percent;
}
export function verifiedCount(s: State, courseId: string) {
  return s.verified.filter(
    (id) =>
      s.sessions.find((session) => session.id === id)?.courseId === courseId,
  ).length;
}
export function pendingCount(s: State, courseId: string) {
  return s.sessions.filter(
    (session) => session.courseId === courseId && session.status === "studied",
  ).length;
}
export function balance(s: State, hours: number): State {
  const planned = s.sessions.filter((x) => x.status === "planned");
  const perSession = Math.max(
    10,
    Math.min(60, Math.floor((hours * 60) / Math.max(1, planned.length))),
  );
  return {
    ...s,
    hours,
    sessions: s.sessions.map((x) =>
      x.status === "planned" ? { ...x, minutes: perSession } : x,
    ),
  };
}
export function readState(): State {
  try {
    const x = JSON.parse(localStorage.getItem("pathly.demo.v1") || "null");
    if (
      (x?.version === 1 || x?.version === 2) &&
      Array.isArray(x.active) &&
      Array.isArray(x.sessions) &&
      Array.isArray(x.verified) &&
      Array.isArray(x.future) &&
      Array.isArray(x.messages) &&
      typeof x.name === "string" &&
      typeof x.hours === "number"
    ) {
      const currentDate = dateKey(today());
      const savedDate =
        typeof x.scheduleDate === "string"
          ? x.scheduleDate
          : x.sessions.find((session: Session) => session.id === "past")?.date;
      if (!savedDate || savedDate === currentDate)
        return { ...x, version: 2, scheduleDate: currentDate };

      const parseDate = (value: string) => {
        const [year, month, day] = value.split("-").map(Number);
        return new Date(year, month - 1, day);
      };
      const elapsedDays = Math.round(
        (parseDate(currentDate).getTime() - parseDate(savedDate).getTime()) /
          86_400_000,
      );
      return {
        ...x,
        version: 2,
        scheduleDate: currentDate,
        sessions: x.sessions.map((session: Session) => ({
          ...session,
          date: dateKey(addDays(parseDate(session.date), elapsedDays)),
        })),
      };
    }
  } catch {
    /* Invalid storage falls back to a fresh demo. */
  }
  return initialState();
}
