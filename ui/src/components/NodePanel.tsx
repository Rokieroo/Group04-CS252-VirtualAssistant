import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type { Edge, NodeStatus } from "../api/core";
import type { RoadmapNode } from "../api/types";
import { nodeSources, type NodeSources } from "../api/materials";
import { fetchNodeExercises, type ExerciseItem } from "../api/exercises";
import { searchNodeResources } from "../api/resources";
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
};

export function NodePanel({
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
}: NodePanelProps) {
  const [sourcesData, setSourcesData] = useState<NodeSources | null>(null);
  const [exercises, setExercises] = useState<ExerciseItem[]>([]);
  const [exercisesCount, setExercisesCount] = useState(0);
  const [searching, setSearching] = useState(false);
  const [loadError, setLoadError] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);
  const loadVersion = useRef(0);

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
    if (sourceResult.status === "fulfilled") setSourcesData(sourceResult.value);
    else
      setLoadError(
        sourceResult.reason instanceof Error
          ? sourceResult.reason.message
          : "Không tải được nguồn học.",
      );
    if (exerciseResult.status === "fulfilled") {
      setExercises(exerciseResult.value.exercises);
      setExercisesCount(exerciseResult.value.count);
    }
  }, []);

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

  if (!isOpen || !node) return null;

  // Prerequisite and dependent connections
  const prereqEdges = edges.filter((e) => e.child_id === node.id);
  const unlockEdges = edges.filter((e) => e.parent_id === node.id);

  const prereqNodes = prereqEdges
    .map((e) => allNodes.find((n) => n.id === e.parent_id))
    .filter((n): n is RoadmapNode => Boolean(n));

  const unlockNodes = unlockEdges
    .map((e) => allNodes.find((n) => n.id === e.child_id))
    .filter((n): n is RoadmapNode => Boolean(n));

  // Compute learning path (ancestors leading to this node)
  const handleHighlightPath = () => {
    const visited = new Set<string>();
    const queue = [node.id];
    while (queue.length > 0) {
      const curr = queue.shift()!;
      if (!visited.has(curr)) {
        visited.add(curr);
        const parents = edges
          .filter((e) => e.child_id === curr)
          .map((e) => e.parent_id);
        queue.push(...parents);
      }
    }
    onHighlightPath?.(Array.from(visited));
  };

  const handleRetrySearch = async () => {
    setSearching(true);
    try {
      await searchNodeResources(node.id);
      await loadData(node.id);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Không bắt đầu tìm lại được.",
      );
    } finally {
      setSearching(false);
    }
  };

  // Sources categorized
  const ownMaterials =
    sourcesData?.sources.filter((s) => s.kind === "user_material") || [];
  const catalogSources: VerifiedSource[] = (
    sourcesData?.sources.filter((s) => s.kind !== "user_material") || []
  ).map((s) => ({
    ...s,
    institution: s.institution ?? undefined,
    verification_status:
      s.kind === "catalog" && s.verification_status === "verified"
        ? "verified"
        : undefined,
  }));

  const isInsufficient = sourcesData?.status === "insufficient";

  const isMilestone = node.type === "milestone" || node.kind === "milestone";
  const coveredNodes = (node.covers || [])
    .map((cid: string) => allNodes.find((n: RoadmapNode) => n.id === cid))
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
        aria-label={`Chi tiết chặng: ${node.title}`}
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
              aria-label="Đóng bảng thông tin chặng (Esc)"
              title="Đóng (Esc)"
            >
              ✕
            </button>
          </div>

          <div className="np-meta-chips">
            {node.week && <span className="np-chip">Tuần {node.week}</span>}
            {(node.est_minutes || node.duration_minutes) && (
              <span className="np-chip">
                ⏱ {node.est_minutes || node.duration_minutes} phút
              </span>
            )}
            {node.status && (
              <span className={`np-chip status-${node.status}`}>
                Trạng thái: {node.status}
              </span>
            )}
            {node.outcome_ids &&
              node.outcome_ids.map((clo: string) => (
                <span
                  key={clo}
                  className="np-chip"
                  title="Chuẩn đầu ra môn học"
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
                title="Mở giáo trình tại trang này"
              >
                📄 Trang syllabus: {node.syllabus_page} ↗
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
              {node.due_at && <span>📅 Hạn chót: {node.due_at}</span>}
              {node.weight !== undefined && (
                <span>⚖ Trọng số: {node.weight}%</span>
              )}
              {coveredNodes.length > 0 && (
                <span>
                  Bao phủ {coveredNodes.length} chặng (
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
            Xem đồ thị cục bộ
          </button>
        )}
        {/* 2. Scrollable Body Content */}
        <div className="np-body" aria-live="polite">
          {/* Prerequisite & Unlocked Nodes */}
          <section className="np-section" aria-label="Quan hệ tiên quyết">
            <div className="np-section-header">
              <h4 className="np-section-title">Liên kết học tập</h4>
              <button
                type="button"
                className="np-path-btn"
                disabled={!onHighlightPath}
                onClick={handleHighlightPath}
                title="Tô sáng đường dẫn học tập từ đầu đến chặng này"
              >
                🛣 Đường học tới đây
              </button>
            </div>

            <div>
              <span
                style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
              >
                Cần học trước ({prereqNodes.length}):
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
                    Không có tiên quyết
                  </span>
                )}
              </div>
            </div>

            <div style={{ marginTop: "0.4rem" }}>
              <span
                style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
              >
                Mở khóa ({unlockNodes.length}):
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
                    Không mở khóa thêm
                  </span>
                )}
              </div>
            </div>
          </section>

          {/* 3. Learning Sources (Spec 114 User Materials First, then Catalog) */}
          <section
            className="np-section"
            aria-label="Nguồn học tập đã kiểm chứng"
          >
            <h4 className="np-section-title">Nguồn học tập</h4>

            {/* User uploaded materials always first (#114) */}
            {ownMaterials.length > 0 && (
              <div
                className="np-user-materials-list"
                aria-label="Tài liệu riêng của bạn"
              >
                {ownMaterials.map((s) => (
                  <div key={s.id} className="np-user-material-item">
                    <span className="np-user-material-title">📂 {s.title}</span>
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
                            title={`Mở tài liệu tại trang ${p}`}
                          >
                            Trang {p} ↗
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {loadError && (
              <div>
                <p role="alert" className="row-error">
                  {loadError}
                </p>
                <button
                  className="button"
                  onClick={() => void loadData(node.id)}
                >
                  Thử lại thông tin chặng
                </button>
              </div>
            )}

            {/* Insufficient State Banner */}
            {isInsufficient && (
              <InsufficientSourcesNotice
                onRetry={handleRetrySearch}
                busy={searching}
              />
            )}

            {/* Verified Catalog Sources using Shared VerifiedSourceCard (#104) */}
            {catalogSources.length > 0 && (
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
                  />
                ))}
              </div>
            )}
          </section>

          {/* 4. Practice Exercises Preview (#115) */}
          <section
            className="np-section"
            aria-label="Bài luyện tập có trích dẫn"
          >
            <div className="np-section-header">
              <h4 className="np-section-title">
                Bài tập (
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
                  Luyện tập chặng này
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
                      📖 Trích dẫn:{" "}
                      <strong>
                        {ex.citation.institution || ex.citation.title}
                        {ex.citation.page ? ` · Trang ${ex.citation.page}` : ""}
                      </strong>
                    </span>
                  </div>
                ))
              ) : (
                <span
                  style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}
                >
                  Chưa tìm thấy bài luyện tập có trích dẫn cho chặng này.
                </span>
              )}
            </div>
          </section>
        </div>

        {/* 5. Action Gateways Footer */}
        <footer className="np-footer">
          {(!onAskQuestion || !onOpenPractice) && (
            <p className="sm">
              Hỏi đáp và luyện tập theo chặng hiện chưa khả dụng.
            </p>
          )}
          <div className="np-footer-buttons">
            <button
              type="button"
              className="np-btn-primary"
              disabled={!onOpenFullStage}
              onClick={() => onOpenFullStage?.(node.id)}
            >
              Trang chặng (S6)
            </button>
            <button
              type="button"
              className="np-btn-secondary"
              disabled={!onAskQuestion}
              onClick={() => onAskQuestion?.(node.id)}
            >
              Hỏi đáp AI (S10)
            </button>
            <button
              type="button"
              className="np-btn-secondary"
              disabled={!onScheduleNode}
              onClick={() => onScheduleNode?.(node.id)}
            >
              {scheduleScope === "course"
                ? "Xếp lịch lộ trình (S7)"
                : "Xếp vào lịch (S7)"}
            </button>
          </div>
        </footer>
      </aside>
    </>
  );
}
