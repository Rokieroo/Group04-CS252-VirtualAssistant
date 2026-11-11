import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../api/backend";
import {
  createsRoadmapCycle,
  liveCoreService,
  type CoreService,
  type Edge,
  type RoadmapDraft,
  type SyllabusDraft,
  type UploadOptions,
} from "../api/core";
import { ERRORS } from "../concepts";
import { mockCoreService } from "../api/mockCore";
import { fetchSavedSyllabus, validateDraft } from "../api/syllabus";
import { explain } from "./text";

/** Where the learner is in the core loop: syllabus in → reviewed → roadmap proposed → roadmap approved. */
export type Stage = "upload" | "review" | "plan" | "ready";
export type StudyPlan = Awaited<ReturnType<CoreService["schedule"]>>;

type Saved = {
  draft: SyllabusDraft | null;
  roadmap: RoadmapDraft | null;
  stage: Stage;
  plan: StudyPlan | null;
};

// The preview keeps the whole course in this tab; the real app only remembers which roadmap to reopen.
const PREVIEW_KEY = "pathly.preview.course";
const LIVE_KEY = "pathly.course";

function read<T>(storage: () => Storage, key: string): T | null {
  try {
    return JSON.parse(storage().getItem(key) || "null") as T | null;
  } catch {
    return null;
  }
}
function write(storage: () => Storage, key: string, value: unknown) {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the course lasts for this visit */
  }
}

function loadPreview(): Saved | null {
  const saved = read<Saved>(() => sessionStorage, PREVIEW_KEY);
  if (!saved || !["upload", "review", "plan", "ready"].includes(saved.stage)) return null;
  if (saved.stage !== "upload" && !saved.draft) return null;
  if ((saved.stage === "plan" || saved.stage === "ready") && !saved.roadmap) return null;
  // The preview service keeps the confirmed syllabus in memory only, so a reload asks to confirm again.
  if (saved.stage === "review" && saved.draft) saved.draft = { ...saved.draft, status: "draft" };
  return saved;
}

/** Forget the course this browser remembers (sign-out, or starting over). */
export function forgetCourse() {
  write(() => sessionStorage, PREVIEW_KEY, null);
  write(() => localStorage, LIVE_KEY, null);
}

/**
 * The one course of the app and every step of its core loop. Screens read this state and
 * call these actions; none of them talks to the syllabus or roadmap services directly.
 */
export function useCourse(mock: boolean) {
  const service: CoreService = mock ? mockCoreService : liveCoreService;
  const [initial] = useState(() => (mock ? loadPreview() : null));
  const [draft, setDraft] = useState<SyllabusDraft | null>(initial?.draft ?? null);
  const [roadmap, setRoadmap] = useState<RoadmapDraft | null>(initial?.roadmap ?? null);
  const [stage, setStage] = useState<Stage>(initial?.stage ?? "upload");
  const [plan, setPlan] = useState<StudyPlan | null>(initial?.plan ?? null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [weekly, setWeekly] = useState(300);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [restoring, setRestoring] = useState(
    () => !mock && Boolean(read<{ roadmapId: string }>(() => localStorage, LIVE_KEY)?.roadmapId),
  );
  const working = useRef(false);

  useEffect(() => {
    if (mock) write(() => sessionStorage, PREVIEW_KEY, { draft, roadmap, stage, plan });
  }, [mock, draft, roadmap, stage, plan]);

  // Reopen the approved roadmap of the last visit; a roadmap that is gone just starts the setup again.
  useEffect(() => {
    const id = mock ? null : read<{ roadmapId: string }>(() => localStorage, LIVE_KEY)?.roadmapId;
    if (!id) return;
    let current = true;
    (async () => {
      try {
        const saved = await call<RoadmapDraft>(`/roadmaps/${encodeURIComponent(id)}`);
        const edges = await call<Edge[]>(`/roadmaps/${encodeURIComponent(id)}/edges`);
        const syllabus = saved.course_id
          ? await fetchSavedSyllabus(saved.course_id).catch(() => null)
          : null;
        if (!current) return;
        setRoadmap({ ...saved, edges, overloaded_weeks: saved.overloaded_weeks || [] });
        setDraft(syllabus);
        setStage("ready");
      } catch {
        write(() => localStorage, LIVE_KEY, null);
      } finally {
        if (current) setRestoring(false);
      }
    })();
    return () => {
      current = false;
    };
  }, [mock]);

  const run = useCallback(async (work: () => Promise<void>) => {
    if (working.current) return false;
    working.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
      return true;
    } catch (e) {
      setError(explain(e));
      return false;
    } finally {
      working.current = false;
      setBusy(false);
    }
  }, []);

  const warnings = draft ? validateDraft(draft) : [];
  const blocked = warnings.some((w) => w.blocking);

  const upload = (input: File | string, options?: UploadOptions) =>
    run(async () => {
      const result = await service.upload(input, options);
      setDraft(result);
      setRoadmap(null);
      setPlan(null);
      setSelectedId(null);
      setStage("review");
    });

  /** Any edit reopens the review: a confirmed syllabus must be confirmed again. */
  const update = (change: Partial<SyllabusDraft>) =>
    setDraft((current) => current && { ...current, ...change, status: "draft" });

  /** One action for the learner: save the reviewed syllabus, then propose its roadmap. */
  const confirmAndGenerate = () =>
    run(async () => {
      if (!draft || blocked) return;
      const saved = draft.status === "confirmed" ? draft : await service.confirm(draft);
      setDraft(saved);
      setRoadmap(await service.generate(saved.id, saved.course_id));
      setSelectedId(null);
      setStage("plan");
    });

  const approve = () =>
    run(async () => {
      if (!roadmap) return;
      const saved = await service.save(roadmap);
      setRoadmap(saved);
      setStage("ready");
      if (!mock) write(() => localStorage, LIVE_KEY, { roadmapId: saved.id });
    });

  /** Reopen the reviewed syllabus; after a reload it is fetched from the server first. */
  const editSyllabus = () =>
    run(async () => {
      if (!draft) {
        if (!roadmap?.course_id) throw new Error("Chưa có đề cương đã lưu cho lộ trình này.");
        setDraft(await fetchSavedSyllabus(roadmap.course_id));
      }
      setStage("review");
    });

  const startOver = () => {
    forgetCourse();
    setDraft(null);
    setRoadmap(null);
    setPlan(null);
    setSelectedId(null);
    setError("");
    setStage("upload");
  };

  /** Adds "learn parent before child". Resolves to an error sentence, or null when the link was added. */
  const addEdge = async (parentId: string, childId: string): Promise<string | null> => {
    if (!roadmap || !parentId || !childId || parentId === childId) return null;
    if (roadmap.edges.some((e) => e.parent_id === parentId && e.child_id === childId)) return null;
    if (createsRoadmapCycle(roadmap.edges, parentId, childId)) return ERRORS.cycle;
    const id = roadmap.id;
    try {
      const edge: Edge =
        !mock && stage === "ready"
          ? await call<Edge>(`/roadmaps/${encodeURIComponent(id)}/graph/edges`, {
              method: "POST",
              body: JSON.stringify({ parent_id: parentId, child_id: childId, kind: "strict" }),
            })
          : { parent_id: parentId, child_id: childId, kind: "strict", origin: "user", confidence: 1 };
      setRoadmap((current) =>
        current?.id === id ? { ...current, edges: [...current.edges, edge] } : current,
      );
      return null;
    } catch (e) {
      return explain(e);
    }
  };

  const removeEdge = async (edge: Pick<Edge, "parent_id" | "child_id">): Promise<string | null> => {
    if (!roadmap) return null;
    const id = roadmap.id;
    try {
      if (!mock && stage === "ready")
        await call(
          `/roadmaps/${encodeURIComponent(id)}/graph/edges/${encodeURIComponent(edge.parent_id)}/${encodeURIComponent(edge.child_id)}`,
          { method: "DELETE" },
        );
      setRoadmap((current) =>
        current?.id === id
          ? {
              ...current,
              edges: current.edges.filter(
                (e) => e.parent_id !== edge.parent_id || e.child_id !== edge.child_id,
              ),
            }
          : current,
      );
      return null;
    } catch (e) {
      return explain(e);
    }
  };

  /** Put every step of the approved roadmap on the calendar within the given study time. */
  const schedule = (weeklyMinutes: number, dailyMinutes: number) =>
    run(async () => {
      if (!roadmap) return;
      await service.save(roadmap);
      setPlan(await service.schedule(roadmap.id, weeklyMinutes, dailyMinutes));
    });

  return {
    mock,
    draft,
    roadmap,
    stage,
    setStage,
    plan,
    selectedId,
    setSelectedId,
    weekly,
    setWeekly,
    busy,
    error,
    clearError: () => setError(""),
    restoring,
    warnings,
    blocked,
    upload,
    update,
    confirmAndGenerate,
    approve,
    editSyllabus,
    startOver,
    addEdge,
    removeEdge,
    schedule,
  };
}

export type Course = ReturnType<typeof useCourse>;
