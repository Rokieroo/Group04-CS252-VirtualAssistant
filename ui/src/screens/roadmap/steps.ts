import type { NodeStatus, RoadmapDraft } from "../../api/core";

/** One step of the roadmap: a topic to learn, or a milestone (exam, deadline) that tests topics. */
export type Step = RoadmapDraft["nodes"][number];

export const isMilestone = (step: Step) => step.type === "milestone";
export const minutesOf = (step: Step) => step.est_minutes ?? step.duration_minutes ?? 0;
export const statusOf = (step: Step): NodeStatus => step.status ?? "available";

/** Steps grouped by week in order; inside a week the topics come before the milestones that test them. */
export function byWeek(steps: Step[]): { week: number; steps: Step[] }[] {
  const weeks = new Map<number, Step[]>();
  for (const step of steps) {
    const week = step.week ?? 1;
    weeks.set(week, [...(weeks.get(week) ?? []), step]);
  }
  return [...weeks.entries()]
    .sort(([a], [b]) => a - b)
    .map(([week, list]) => ({
      week,
      steps: [...list.filter((s) => !isMilestone(s)), ...list.filter(isMilestone)],
    }));
}

/** Progress counts topics only: a milestone is a date to be ready for, not something to tick off. */
export function progressOf(steps: Step[]) {
  const topics = steps.filter((s) => !isMilestone(s));
  const done = topics.filter((s) => statusOf(s) === "done").length;
  return {
    done,
    total: topics.length,
    percent: topics.length ? Math.round((done / topics.length) * 100) : 0,
  };
}

/** The first week that still has a topic to learn, and the first milestone from that week on. */
export function nextUp(steps: Step[]) {
  const weeks = byWeek(steps);
  const current =
    weeks.find((w) => w.steps.some((s) => !isMilestone(s) && statusOf(s) !== "done")) ?? null;
  const milestone =
    weeks
      .filter((w) => !current || w.week >= current.week)
      .flatMap((w) => w.steps)
      .find(isMilestone) ?? null;
  return { current, milestone };
}
