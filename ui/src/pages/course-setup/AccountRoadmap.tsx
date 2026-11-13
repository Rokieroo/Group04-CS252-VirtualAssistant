import { useEffect, useState } from "react";
import { call } from "../../api/backend";
import type { Edge, RoadmapDraft } from "../../api/core";
import type { OwnedCourse } from "../CourseLibrary";
import { RootRoadmap, type RootCourse } from "./RootRoadmap";

type Entry = { course: OwnedCourse; saved?: RoadmapDraft; failed?: boolean };

async function loadCourse(course: OwnedCourse): Promise<Entry> {
  try {
    const versions = await call<RoadmapDraft[]>(
      `/courses/${encodeURIComponent(course.id)}/roadmaps`,
    );
    const latest = versions[0];
    if (!latest) return { course };
    const edges = await call<Edge[]>(
      `/roadmaps/${encodeURIComponent(latest.id)}/edges`,
    );
    return { course, saved: { ...latest, edges } };
  } catch {
    return { course, failed: true };
  }
}

export function AccountRoadmap({
  current,
  onOpen,
}: {
  current: RoadmapDraft | null;
  onOpen?: (course: OwnedCourse, roadmapId?: string, resume?: boolean) => void;
}) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setError("");
    call<OwnedCourse[]>("/courses")
      .then((courses) => Promise.all(courses.map(loadCourse)))
      .then((result) => {
        if (!cancelled) setEntries(result);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [revision]);

  const paths: RootCourse[] = [];
  const available = new Map<string, Entry>();
  const failures: string[] = [];
  for (const entry of entries ?? []) {
    const { course } = entry;
    const saved = current?.course_id === course.id ? current : entry.saved;
    if (!saved && entry.failed) {
      failures.push(course.title);
      continue;
    }
    available.set(course.id, { course, saved });
    paths.push({
      id: course.id,
      title: course.title,
      actionLabel: saved ? "Open roadmap" : "Continue course setup",
      edges: saved?.edges,
      nodes: (saved?.nodes ?? []).map((n) => ({
        ...n,
        minutes: n.est_minutes ?? n.duration_minutes ?? undefined,
        description: `${n.title}${n.week ? ` · Week ${n.week}` : ""}. ${n.type === "milestone" ? "Assessment milestone." : "A learning checkpoint from your reviewed syllabus."}`,
      })),
    });
  }
  return (
    <>
      {(error || failures.length > 0) && (
        <div role="alert">
          {error || `Could not load paths for ${failures.join(", ")}.`}{" "}
          <button onClick={() => setRevision((v) => v + 1)}>Retry</button>
        </div>
      )}
      {!entries && !error && <p role="status">Loading course paths…</p>}
      {entries && (
        <RootRoadmap
          courses={paths}
          activeId={current?.course_id}
          onOpen={(id) => {
            const entry = available.get(id);
            if (entry && (!current || current.id !== entry.saved?.id))
              onOpen?.(entry.course, entry.saved?.id, !entry.saved);
          }}
        />
      )}
    </>
  );
}
