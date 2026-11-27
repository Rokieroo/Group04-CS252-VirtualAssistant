import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type { Edge, NodeStatus } from "../api/core";
import type { RoadmapNode } from "../api/types";
import { editLibrary, type SourceState } from "../api/personalLibrary";
import { nodeSources, type NodeSources } from "../api/materials";
import { fetchNodeExercises, type ExerciseItem } from "../api/exercises";
import { searchNodeResources } from "../api/resources";
import type { Known } from "../api/placement";
import {
  InsufficientSourcesNotice,
  VerifiedSourceCard,
  type VerifiedSource,
} from "./VerifiedSourceCard";
import "./NodePanel.css";

export type ExtendedNode = RoadmapNode & {
  status?: NodeStatus;
  outcome_ids?: string[];
  syllabus_page?: number;
  weight?: number;
  est_minutes?: number | null;
};

export type NodePanelProps = {
  persistLibrary?: boolean;
  manageUrl?: boolean;
  scheduleScope?: "node" | "course";
  roadmapId: string;
  node: ExtendedNode | null;
  allNodes: (RoadmapNode & { status?: NodeStatus })[];
  edges: Edge[];
  isOpen: boolean;
  onClose: () => void;
  onSelectNode?: (nodeId: string) => void;
  onLocalGraph?: (nodeId: string) => void;
  onHighlightPath?: (pathNodeIds: string[]) => void;
  onOpenFullStage?: (nodeId: string) => void;
  onAskQuestion?: (nodeId: string) => void;
  onScheduleNode?: (nodeId: string) => void;
  onOpenSyllabusPage?: (page: number) => void;
  onOpenMaterialPage?: (sourceId: string, page: number) => void;
  onOpenPractice?: (nodeId: string, exerciseIds?: string[]) => void;
  known?: Known | null;
  onToggleKnown?: (nodeId: string, known: boolean) => void;
};

export function NodePanel({
  persistLibrary = false,
  manageUrl = true,
  scheduleScope = "node",
  roadmapId,
  node,
  allNodes,
  edges,
  isOpen,
  onClose,
  onSelectNode,
  onLocalGraph,
  onHighlightPath,
  onOpenFullStage,
  onAskQuestion,
  onScheduleNode,
  onOpenSyllabusPage,
  onOpenMaterialPage,
  onOpenPractice,
  known = null,
  onToggleKnown,
}: NodePanelProps) {
  const [sourcesData, setSourcesData] = useState<NodeSources | null>(null);
  const [exercises, setExercises] = useState<ExerciseItem[]>([]);
  const [exercisesCount, setExercisesCount] = useState(0);
  const [searching, setSearching] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [pinnedSourceIds, setPinnedSourceIds] = useState<Set<string>>(new Set());
  const [hiddenSourceIds, setHiddenSourceIds] = useState<Set<string>>(new Set());
  const [exitingSourceIds, setExitingSourceIds] = useState<Set<string>>(new Set());
  const panelRef = useRef<HTMLDivElement>(null);
  const loadVersion = useRef(0);
  const feedbackTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map(),
  );

  const clearFeedbackTimers = useCallback(() => {
    for (const timer of feedbackTimersRef.current.values()) {
      clearTimeout(timer);
    }
    feedbackTimersRef.current.clear();
  }, []);

  // Update URL hash for deep-linking: /roadmaps/{id}/graph/{node} (Issue #109 requirement 1)
  useEffect(() => {
    if (manageUrl && isOpen && node) {
      const prevHash = window.location.hash;
      const targetHash = `roadmaps/${encodeURIComponent(roadmapId)}/graph/${encodeURIComponent(node.id)}`;
      if (!window.location.hash.includes(targetHash)) {
        window.history.replaceState(null, "", `#${targetHash}`);
      }
      return () => {
        if (window.location.hash.includes(targetHash)) {
          window.history.replaceState(null, "", prevHash || "#roadmap");
        }
      };
    }
  }, [isOpen, node, roadmapId, manageUrl]);

  // Load sources and exercises for current node
  const loadData = useCallback(async (nodeId: string) => {
    const version = ++loadVersion.current;
    setSourcesData(null);
    setExercises([]);
    setExercisesCount(0);
    setLoadError("");
    const [sourceResult, exerciseResult] = await Promise.allSettled([
      nodeSources(nodeId),
      fetchNodeExercises(nodeId, 5),
    ]);
    if (version !== loadVersion.current) return;
    if (sourceResult.status === "fulfilled") {
      setSourcesData(sourceResult.value);
      setPinnedSourceIds(new Set(sourceResult.value.sources.filter(s=>s.personal_state==="pinned").map(s=>s.id)));
      setHiddenSourceIds(new Set(sourceResult.value.sources.filter(s=>s.personal_state==="hidden").map(s=>s.id)));
    }
    else
      setLoadError(
        sourceResult.reason instanceof Error
          ? sourceResult.reason.message
          : "Could not load learning sources.",
      );
    if (exerciseResult.status === "fulfilled") {
      setExercises(exerciseResult.value.exercises);
      setExercisesCount(exerciseResult.value.count);
    }
  }, []);

  useEffect(() => {
    clearFeedbackTimers();
    setPinnedSourceIds(new Set());
    setHiddenSourceIds(new Set());
    setExitingSourceIds(new Set());
    setSearching(false);
    return () => clearFeedbackTimers();
  }, [node?.id, clearFeedbackTimers]);

  useEffect(() => {
    if (node && isOpen) void loadData(node.id);
    return () => {
      ++loadVersion.current;
    };
  }, [node?.id, isOpen, loadData]);

  // A modal dialog (#109 step 7): focus moves in on open, Tab stays inside, and
  // focus returns to whatever opened the panel when it closes.
  useEffect(() => {
    if (!isOpen) return;
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => opener?.focus();
  }, [isOpen]);

  const trapFocus = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "Tab" || !panelRef.current) return;
    const focusable = panelRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const nodeById = useMemo(
    () => new Map(allNodes.map((item) => [item.id, item])),
    [allNodes],
  );

  const parentsByChild = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of edges) {
      const list = map.get(edge.child_id);
      if (list) list.push(edge.parent_id);
      else map.set(edge.child_id, [edge.parent_id]);
    }
    return map;
  }, [edges]);

  if (!isOpen || !node) return null;

  // Prerequisite and dependent connections
  const prereqEdges = edges.filter((e) => e.child_id === node.id);
  const unlockEdges = edges.filter((e) => e.parent_id === node.id);

  const prereqNodes = prereqEdges
    .map((e) => nodeById.get(e.parent_id))
    .filter((n): n is RoadmapNode => Boolean(n));

  const unlockNodes = unlockEdges
    .map((e) => nodeById.get(e.child_id))
    .filter((n): n is RoadmapNode => Boolean(n));

  // Compute learning path (ancestors leading to this node)
  const handleHighlightPath = () => {
    const visited = new Set<string>();
    const queue = [node.id];
    for (let head = 0; head < queue.length; head++) {
      const curr = queue[head];
      if (!visited.has(curr)) {
        visited.add(curr);
        const parents = parentsByChild.get(curr);
        if (parents) queue.push(...parents);
      }
    }
    onHighlightPath?.(Array.from(visited));
  };

  const handleRetrySearch = async () => {
    const targetNodeId = node.id;
    const searchVersion = loadVersion.current;
    setSearching(true);
    try {
      await searchNodeResources(targetNodeId);
      if (searchVersion !== loadVersion.current) return;
      await loadData(targetNodeId);
    } catch (err) {
      if (searchVersion !== loadVersion.current) return;
      setLoadError(
        err instanceof Error ? err.message : "Could not restart search.",
      );
    } finally {
      if (searchVersion === loadVersion.current) {
        setSearching(false);
      }
    }
  };

  const saveState = async (sourceId:string,state:SourceState) => {
    const version=loadVersion.current;
    try {
      await editLibrary(node.id,sourceId,{state});
      return version===loadVersion.current;
    } catch(e){if(version===loadVersion.current)setLoadError(String(e));return false;}
  };
  const handleFeedback = async (sourceId: string, helpful: boolean) => {
    if (!helpful) {
      if (persistLibrary && !await saveState(sourceId,"hidden")) return;
      const prevTimer = feedbackTimersRef.current.get(sourceId);
      if (prevTimer) clearTimeout(prevTimer);
      setExitingSourceIds((prev) => new Set(prev).add(sourceId));
      const timer = setTimeout(() => {
        feedbackTimersRef.current.delete(sourceId);
        setHiddenSourceIds((prev) => new Set(prev).add(sourceId));
        setExitingSourceIds((prev) => {
          const next = new Set(prev);
          next.delete(sourceId);
          return next;
        });
      }, 250);
      feedbackTimersRef.current.set(sourceId, timer);
    }
  };

  const handlePin = async (sourceId: string, pinned: boolean) => {
    if (persistLibrary && !await saveState(sourceId,pinned?"pinned":"none")) return;
    setPinnedSourceIds((prev) => {
      const next = new Set(prev);
      if (pinned) next.add(sourceId);
      else next.delete(sourceId);
      return next;
    });
  };

  // Sources categorized into three distinct groups (Issue #159)
  const rawSources = sourcesData?.sources || [];
  const visibleSources: VerifiedSource[] = rawSources
    .filter((s) => !hiddenSourceIds.has(s.id))
    .map((s) => ({
      ...s,
      institution: s.institution ?? undefined,
      verification_status:
        s.kind === "catalog" && s.verification_status === "verified"
          ? "verified"
          : undefined,
      pinned: pinnedSourceIds.has(s.id),
    }))
    .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));

  const ownMaterials: VerifiedSource[] = [];
  const catalogSources: VerifiedSource[] = [];
  const externalSources: VerifiedSource[] = [];
  for (const source of visibleSources) {
    if (source.kind === "user_material") ownMaterials.push(source);
    else if (source.kind === "catalog") catalogSources.push(source);
    else if (source.kind === "external" || source.kind === "web")
      externalSources.push(source);
  }

  const isInsufficient = sourcesData?.status === "insufficient";

  const isMilestone = node.type === "milestone" || node.kind === "milestone";
  const coveredNodes = (node.covers || [])
    .map((cid: string) => nodeById.get(cid))
    .filter((n): n is RoadmapNode => Boolean(n));

  return (
    <>
      {/* Backdrop Scrim */}
      <div
        className="node-panel-scrim"
        onClick={onClose}
        aria-hidden="true"
        data-testid="node-panel-scrim"
      />

      {/* Main Drawer / Bottom Sheet */}
      <aside
        ref={panelRef}
        className="node-panel-container"
        role="dialog"
        aria-modal="true"
        aria-label={`Stage details: ${node.title}`}
        tabIndex={-1}
        onKeyDown={trapFocus}
      >
        <div className="node-panel-drag-handle" aria-hidden="true" />

        {/* 1. Header */}
        <header className="np-header">
          <div className="np-header-top">
            <h3 className="np-title">
              {isMilestone ? "💎 " : "📍 "}
              {node.title}
            </h3>
            <button
              type="button"
              className="np-close-btn"
              onClick={onClose}
              aria-label="Close stage details panel (Esc)"
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>

          <div className="np-meta-chips">
            {node.week && <span className="np-chip">Week {node.week}</span>}
            {(node.est_minutes || node.duration_minutes) && (
              <span className="np-chip">
                ⏱ {node.est_minutes || node.duration_minutes} min
              </span>
            )}
            {node.status && (
              <span className={`np-chip status-${node.status}`}>
                Status: {node.status}
              </span>
            )}
            {node.outcome_ids &&
              node.outcome_ids.map((clo: string) => (
                <span
                  key={clo}
                  className="np-chip"
                  title="Course learning outcome"
                >
                  🎯 {clo}
                </span>
              ))}
            {node.syllabus_page && (
              <button
                type="button"
                className="np-chip np-chip-clickable"
                disabled={!onOpenSyllabusPage}
                onClick={() => onOpenSyllabusPage?.(node.syllabus_page!)}
                title="Open syllabus at this page"
              >
                📄 Syllabus page: {node.syllabus_page} ↗
              </button>
            )}
          </div>

          {/* Milestone specific details */}
          {isMilestone && (
            <div
              className="np-meta-chips"
              style={{
                marginTop: "0.25rem",
                color: "var(--color-primary-ink)",
              }}
            >
              {node.due_at && <span>📅 Due: {node.due_at}</span>}
              {node.weight !== undefined && (
                <span>⚖ Weight: {node.weight}%</span>
              )}
              {coveredNodes.length > 0 && (
                <span>
                  Covers {coveredNodes.length} stages (
                  {coveredNodes.map((c: RoadmapNode) => c.title).join(", ")})
                </span>
              )}
            </div>
          )}
        </header>

        {onLocalGraph && (
          <button
            type="button"
            className="np-path-btn"
            onClick={() => onLocalGraph(node.id)}
          >
            View local graph
          </button>
        )}
        {onToggleKnown && node.type !== "milestone" && (
          <div className="np-known">
            {known && (
              <span className="sm">
                Known (
                {known === "tested"
                  ? "via placement test"
                  : known === "inferred"
                    ? "inferred from answers"
                    : "marked by you"}
                ) — excluded from schedule.
              </span>
            )}
            <button
              type="button"
              className="np-path-btn"
              aria-pressed={Boolean(known)}
              onClick={() => onToggleKnown(node.id, !known)}
            >
              {known ? "Unmark as known" : "I already know this stage"}
            </button>
          </div>
        )}
        {/* 2. Scrollable Body Content */}
        <div className="np-body" aria-live="polite">
          {/* Prerequisite & Unlocked Nodes */}
          <section className="np-section" aria-label="Prerequisites">
            <div className="np-section-header">
              <h4 className="np-section-title">Learning connections</h4>
              <button
                type="button"
                className="np-path-btn"
                disabled={!onHighlightPath}
                onClick={handleHighlightPath}
                title="Highlight the learning path from the start to this stage"
              >
                🛣 Path to here
              </button>
            </div>

            <div>
              <span
                style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
              >
                Prerequisites ({prereqNodes.length}):
              </span>
              <div className="np-node-links" style={{ marginTop: "0.25rem" }}>
                {prereqNodes.length > 0 ? (
                  prereqNodes.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="np-node-pill"
                      onClick={() => onSelectNode?.(p.id)}
                    >
                      ← {p.title}
                    </button>
                  ))
                ) : (
                  <span
                    style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}
                  >
                    No prerequisites
                  </span>
                )}
              </div>
            </div>

            <div style={{ marginTop: "0.4rem" }}>
              <span
                style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
              >
                Unlocks ({unlockNodes.length}):
              </span>
              <div className="np-node-links" style={{ marginTop: "0.25rem" }}>
                {unlockNodes.length > 0 ? (
                  unlockNodes.map((u) => (
                    <button
                      key={u.id}
                      type="button"
                      className="np-node-pill"
                      onClick={() => onSelectNode?.(u.id)}
                    >
                      → {u.title}
                    </button>
                  ))
                ) : (
                  <span
                    style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}
                  >
                    Unlocks no further stages
                  </span>
                )}
              </div>
            </div>
          </section>

          {/* 3. Learning Sources (Spec 114 User Materials First, then Catalog, then External) */}
          <section
            className="np-section"
            aria-label="Recommended learning sources in three groups"
          >
            <h4 className="np-section-title">Recommended learning sources</h4>

            {/* Loading State */}
            {sourcesData === null && !loadError && (
              <div className="np-loading-sources" role="status">
                <span>⏳ Loading recommended sources…</span>
              </div>
            )}

            {/* Error State */}
            {loadError && (
              <div>
                <p role="alert" className="row-error">
                  {loadError}
                </p>
                <button
                  className="button"
                  type="button"
                  onClick={() => void loadData(node.id)}
                >
                  Retry stage details
                </button>
              </div>
            )}

            {/* Group 1: User uploaded materials always first (#114) */}
            {ownMaterials.length > 0 && (
              <div
                className="np-source-group np-group-user-material"
                aria-label="Your personal materials"
              >
                <h5 className="np-group-title">📂 Your materials</h5>
                <div className="np-user-materials-list">
                  {ownMaterials.map((s) => (
                    <div
                      key={s.id}
                      className={`np-user-material-item ${exitingSourceIds.has(s.id) ? "vsc-card-animating-exit" : ""}`}
                    >
                      <div className="np-user-material-header">
                        <span className="np-user-material-title">📂 {s.title}</span>
                        {s.duration_min ? (
                          <span className="vsc-badge vsc-badge-duration">⏱ {s.duration_min} min</span>
                        ) : null}
                      </div>
                      <span
                        style={{
                          fontSize: "0.8rem",
                          color: "var(--color-muted)",
                        }}
                      >
                        {s.reason}
                      </span>
                      {s.pages && s.pages.length > 0 && (
                        <div className="np-page-chips">
                          {s.pages.map((p) => (
                            <button
                              key={p}
                              type="button"
                              className="np-page-btn"
                              disabled={!onOpenMaterialPage}
                              onClick={() =>
                                onOpenMaterialPage?.(s.source_id || s.id, p)
                              }
                              title={`Open material at page ${p}`}
                            >
                              Page {p} ↗
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="vsc-actions" style={{ marginTop: "0.4rem" }}>
                        <button
                          type="button"
                          className="vsc-feedback-btn"
                          onClick={() => handleFeedback(s.id, true)}
                          title="Mark as helpful"
                        >
                          👍 Helpful
                        </button>
                        <button
                          type="button"
                          className="vsc-feedback-btn"
                          onClick={() => handleFeedback(s.id, false)}
                          title="Not helpful"
                        >
                          👎 Not helpful
                        </button>
                        <button
                          type="button"
                          className={`vsc-pin-btn ${s.pinned ? "pinned" : ""}`}
                          onClick={() => handlePin(s.id, !s.pinned)}
                          title={s.pinned ? "Unpin" : "Pin to top"}
                        >
                          {s.pinned ? "📌 Pinned" : "📌 Pin"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Insufficient State Banner */}
            {isInsufficient && (
              <>
                <InsufficientSourcesNotice
                  onRetry={handleRetrySearch}
                  busy={searching}
                />
                <div className="np-insufficient-alternatives" role="note">
                  <p><strong>Suggested alternative references:</strong></p>
                  <ul>
                    <li>Read the course syllabus and primary textbook</li>
                    <li>Review your uploaded lecture slides and personal notes</li>
                    <li>Search additional trusted open educational resources online</li>
                  </ul>
                </div>
              </>
            )}

            {/* Group 2: Verified Catalog Sources using Shared VerifiedSourceCard (#104) */}
            {catalogSources.length > 0 && (
              <div
                className="np-source-group np-group-catalog"
                aria-label="Verified catalog sources"
              >
                <h5 className="np-group-title">✓ Verified catalog sources</h5>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.6rem",
                  }}
                >
                  {catalogSources.map((source) => (
                    <VerifiedSourceCard
                      key={source.id}
                      source={source}
                      compact={true}
                      onFeedback={(helpful) => handleFeedback(source.id, helpful)}
                      onPin={(pinned) => handlePin(source.id, pinned)}
                      className={
                        exitingSourceIds.has(source.id)
                          ? "vsc-card-animating-exit"
                          : "vsc-card-animating-enter"
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Group 3: External Unverified Recommendations (Issue #159) */}
            {externalSources.length > 0 && (
              <div
                className="np-source-group np-group-external"
                aria-label="External source suggestions"
              >
                <h5 className="np-group-title">🌐 External source suggestions</h5>
                <p className="np-group-caption">
                  Web references found online (not yet verified for quality)
                </p>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.6rem",
                  }}
                >
                  {externalSources.map((source) => (
                    <VerifiedSourceCard
                      key={source.id}
                      source={source}
                      compact={true}
                      onFeedback={(helpful) => handleFeedback(source.id, helpful)}
                      onPin={(pinned) => handlePin(source.id, pinned)}
                      className={
                        exitingSourceIds.has(source.id)
                          ? "vsc-card-animating-exit"
                          : "vsc-card-animating-enter"
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Empty state when no sources in any group */}
            {sourcesData !== null && !loadError && visibleSources.length === 0 && !isInsufficient && (
              <p className="np-empty-sources" role="status">
                No recommended sources for this stage yet.
              </p>
            )}
          </section>

          {/* 4. Practice Exercises Preview (#115) */}
          <section
            className="np-section"
            aria-label="Cited practice exercises"
          >
            <div className="np-section-header">
              <h4 className="np-section-title">
                Exercises (
                {exercisesCount > 0 ? exercisesCount : exercises.length})
              </h4>
              {exercises.length > 0 && (
                <button
                  type="button"
                  className="np-path-btn"
                  disabled={!onOpenPractice}
                  onClick={() =>
                    onOpenPractice?.(
                      node.id,
                      exercises.map((e) => e.id),
                    )
                  }
                >
                  Practice this stage
                </button>
              )}
            </div>

            <div className="np-exercises-preview">
              {exercises.length > 0 ? (
                exercises.slice(0, 3).map((ex, idx) => (
                  <div key={ex.id} className="np-exercise-item">
                    <p className="np-exercise-prompt">
                      {idx + 1}. {ex.prompt}
                    </p>
                    <span className="np-citation-chip">
                      📖 Citation:{" "}
                      <strong>
                        {ex.citation.institution || ex.citation.title}
                        {ex.citation.page ? ` · Page ${ex.citation.page}` : ""}
                      </strong>
                    </span>
                  </div>
                ))
              ) : (
                <span
                  style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
                >
                  No cited practice exercises found for this stage yet.
                </span>
              )}
            </div>
          </section>
        </div>

        {/* 5. Action Gateways Footer */}
        <footer className="np-footer">
          {(!onAskQuestion || !onOpenPractice) && (
            <p className="sm">
              Stage Q&amp;A and practice are not available yet.
            </p>
          )}
          <div className="np-footer-buttons">
            <button
              type="button"
              className="np-btn-primary"
              disabled={!onOpenFullStage}
              onClick={() => onOpenFullStage?.(node.id)}
            >
              Stage page (S6)
            </button>
            <button
              type="button"
              className="np-btn-secondary"
              disabled={!onAskQuestion}
              onClick={() => onAskQuestion?.(node.id)}
            >
              Ask AI (S10)
            </button>
            <button
              type="button"
              className="np-btn-secondary"
              disabled={!onScheduleNode}
              onClick={() => onScheduleNode?.(node.id)}
            >
              {scheduleScope === "course"
                ? "Schedule roadmap (S7)"
                : "Add to schedule (S7)"}
            </button>
          </div>
        </footer>
      </aside>
    </>
  );
}
