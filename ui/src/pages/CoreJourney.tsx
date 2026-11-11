import { RootRoadmap, type RootCourse } from "./course-setup/RootRoadmap";
import { tutorial } from "./TutorialCourses";
import { syllabusError, validateDraft } from "../api/syllabus";
import { mockCoreService } from "../api/mockCore";
import { TutorialCourses } from "./TutorialCourses";

import { RoadmapTimeline } from "./course-setup/RoadmapTimeline";
import { SyllabusUpload } from "./course-setup/SyllabusUpload";
import { SyllabusReview } from "./course-setup/SyllabusReview";
import { Modal } from "../components/Modal";
import { GraphCanvas } from "../components/GraphCanvas";
import { GraphFilterBar, type FilterState } from "../components/GraphFilterBar";
import { GraphListView } from "../components/GraphListView";
import { NodePanel } from "../components/NodePanel";
import {
  computeTransitiveReduction,
  computeMilestoneScope,
  computeLocalSubgraph,
} from "../api/graph";
import { useEffect, useRef, useState } from "react";
import type { Page } from "../navigation";
import type { RoadmapNode } from "../api/types";

import {
  createsRoadmapCycle,
  liveCoreService,
  type CoreService,
  type Edge,
  type SyllabusDraft,
  type RoadmapDraft,
  type UploadOptions,
} from "../api/core";
import "./core-journey.css";

const title = (node: RoadmapNode | undefined) =>
  node?.title || "Chặng chưa xác định";
export function CoreJourney({
  page,
  go,
  mock = false,
}: {
  page: Page;
  go: (p: Page) => void;
  mock?: boolean;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const service: CoreService = mock ? mockCoreService : liveCoreService;
  const [draft, setDraft] = useState<SyllabusDraft | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapDraft | null>(null);
  const [stage, setStage] = useState<"upload" | "review" | "plan" | "complete">(
    "upload",
  );
  const [roadmapApproved, setRoadmapApproved] = useState(false);
  const [tutorialEnrolled, setTutorialEnrolled] = useState(false);
  const [removeCourse, setRemoveCourse] = useState(false);
  const [roadmapTab, setRoadmapTab] = useState<"timeline" | "graph">(
    "timeline",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [parent, setParent] = useState("");
  const [child, setChild] = useState("");
  const [graphError, setGraphError] = useState("");
  const [graphLayoutMode, setGraphLayoutMode] = useState<"week" | "force">("week");
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    search: "",
    weekMin: 1,
    weekMax: 15,
    status: "all",
    clo: "",
    verifiedOnly: false,
    hideSoftEdges: false,
    transitiveReduction: false,
    selectedMilestone: "",
    isLocalGraph: false,
    localDepth: 2,
    viewMode: "graph",
  });

  // Filtered nodes and edges for Knowledge Graph (Issue #110)
  const filteredGraphData = (() => {
    if (!roadmap) return { nodes: [], edges: [] };

    let candidateNodes = roadmap.nodes;
    let candidateEdges = roadmap.edges;

    // 1. Milestone scope filter (Exam prep: "Tới mốc kiểm tra")
    if (filters.selectedMilestone) {
      const scope = computeMilestoneScope(
        filters.selectedMilestone,
        roadmap.nodes,
        roadmap.edges,
      );
      candidateNodes = candidateNodes.filter((n) => scope.has(n.id));
      candidateEdges = candidateEdges.filter(
        (e) => scope.has(e.parent_id) && scope.has(e.child_id),
      );
    }

    // 2. Local graph filter
    if (filters.isLocalGraph && selectedGraphNodeId) {
      const localResult = computeLocalSubgraph(
        selectedGraphNodeId,
        filters.localDepth,
        "both",
        candidateNodes,
        candidateEdges,
      );
      candidateNodes = candidateNodes.filter((n) =>
        localResult.nodeIds.has(n.id),
      );
      candidateEdges = localResult.edges;
    }

    // 3. Search query filter
    if (filters.search.trim()) {
      const q = filters.search.toLowerCase().trim();
      candidateNodes = candidateNodes.filter((n) =>
        n.title.toLowerCase().includes(q),
      );
    }

    // 4. Week range filter
    candidateNodes = candidateNodes.filter((n) => {
      const w = n.week ?? 1;
      return w >= filters.weekMin && w <= filters.weekMax;
    });

    // 5. Status filter
    if (filters.status !== "all") {
      candidateNodes = candidateNodes.filter((n) => {
        const s =
          n.status === "done"
            ? "mastered"
            : n.status === "in_progress"
              ? "in_progress"
              : "not_started";
        return s === filters.status;
      });
    }

    const validNodeIds = new Set(candidateNodes.map((n) => n.id));
    candidateEdges = candidateEdges.filter(
      (e) => validNodeIds.has(e.parent_id) && validNodeIds.has(e.child_id),
    );

    // 6. Hide soft edges
    if (filters.hideSoftEdges) {
      candidateEdges = candidateEdges.filter((e) => e.kind !== "soft");
    }

    // 7. Transitive reduction
    if (filters.transitiveReduction) {
      candidateEdges = computeTransitiveReduction(candidateNodes, candidateEdges);
    }

    return { nodes: candidateNodes, edges: candidateEdges };
  })();

  const selectedNodeObj = roadmap
    ? roadmap.nodes.find((n) => n.id === selectedGraphNodeId) ?? null
    : null;

  // Sync URL hash for graph state (Issue #110 requirement 6)
  useEffect(() => {
    if (roadmapTab === "graph") {
      const params = new URLSearchParams();
      if (filters.search) params.set("q", filters.search);
      if (filters.status !== "all") params.set("status", filters.status);
      if (filters.viewMode !== "graph") params.set("view", filters.viewMode);
      if (selectedGraphNodeId) params.set("node", selectedGraphNodeId);
      const queryStr = params.toString();
      const hash = queryStr ? `#graph?${queryStr}` : "#graph";
      window.history.replaceState(null, "", hash);
    }
  }, [roadmapTab, filters, selectedGraphNodeId]);
  const [weekly, setWeekly] = useState(300);
  const [daily, setDaily] = useState(120);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [plan, setPlan] = useState<Awaited<
    ReturnType<CoreService["schedule"]>
  > | null>(null);
  const [sourcePage, setSourcePage] = useState<number | null>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [stage]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  const warnings = draft ? validateDraft(draft) : [];
  const blocked = warnings.some((w) => w.blocking);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(syllabusError(e));
    } finally {
      setBusy(false);
    }
  };
  const load = (file: File | string, options?: UploadOptions) => {
    if (busy) return;
    void run(async () => {
      const result = await service.upload(file, options);
      setDraft(result);
      setRoadmap(null);
      setRoadmapApproved(false);
      setPlan(null);
      setStage("review");
    });
  };
  const update = (change: Partial<SyllabusDraft>) =>
    setDraft(
      (current) => current && { ...current, ...change, status: "draft" },
    );
  const confirm = () => {
    if (!draft || blocked) return;
    void run(async () => {
      const saved = await service.confirm(draft);
      setDraft(saved);
    });
  };
  const generate = () => {
    if (!draft || draft.status !== "confirmed") return;
    void run(async () => {
      setRoadmap(await service.generate(draft.id));
      setStage("plan");
    });
  };
  const approveRoadmap = () => {
    if (!draft || weekly < 25 || weekly > 10080) return;
    void run(async () => {
      if (!roadmap) return;
      setRoadmap(await service.save(roadmap));
      setRoadmapApproved(true);
      setStage("complete");
    });
  };
  const addEdge = (p?: string, c?: string) => {
    const parentId = p ?? parent;
    const childId = c ?? child;
    if (!roadmap || !parentId || !childId) return;
    if (createsRoadmapCycle(roadmap.edges, parentId, childId)) {
      setGraphError("Tạo vòng lặp, hãy bỏ một cạnh.");
      return;
    }
    setGraphError("");
    if (
      !roadmap.edges.some((e) => e.parent_id === parentId && e.child_id === childId)
    )
      setRoadmap({
        ...roadmap,
        edges: [
          ...roadmap.edges,
          {
            parent_id: parentId,
            child_id: childId,
            kind: "strict",
            origin: "user",
            confidence: 1,
          },
        ],
      });
  };
  const removeEdge = (edge: Edge) =>
    roadmap &&
    setRoadmap({ ...roadmap, edges: roadmap.edges.filter((e) => e !== edge) });
  const schedule = () => {
    if (
      !roadmap ||
      busy ||
      !Number.isInteger(weekly) ||
      weekly < 25 ||
      weekly > 10080 ||
      !Number.isInteger(daily) ||
      daily < 25 ||
      daily > 1440
    )
      return;
    void run(async () => {
      await service.save(roadmap);
      setPlan(await service.schedule(roadmap.id, weekly, daily));
      setScheduleOpen(false);
      go("Schedule");
    });
  };
  const topicNodes = roadmap?.nodes.filter((n) => n.type === "topic") || [];
  const sourceChip = (page?: number) =>
    page ? (
      <button
        type="button"
        className="core-citation"
        onClick={() => setSourcePage(page)}
      >
        tr. {page}
      </button>
    ) : (
      <span className="core-no-source">Không có trang nguồn</span>
    );
  const showingRoadmap =
    (page === "Library" && stage === "plan") ||
    (page === "Roadmap" && roadmapApproved);
  return (
    <div className="core-journey">
      {page === "Roadmap" && (
        <RootRoadmap
          courses={
            [
              ...(tutorialEnrolled
                ? [
                    {
                      id: tutorial.id,
                      title: tutorial.title,
                      nodes: tutorial.lessons.map((lesson, i) => ({
                        id: `tutorial-${i}`,
                        title: lesson.title,
                        description: lesson.text,
                        minutes: 2,
                      })),
                    },
                  ]
                : []),
              ...(roadmapApproved && roadmap
                ? [
                    {
                      id: roadmap.id,
                      title:
                        draft?.course?.title?.value?.toString() ||
                        draft?.file_name ||
                        "Your course",
                      nodes: roadmap.nodes.map((n) => ({
                        id: n.id,
                        title: n.title,
                        minutes:
                          n.est_minutes ?? n.duration_minutes ?? undefined,
                        status: n.status,
                        description: `${n.title}${n.week ? ` · Week ${n.week}` : ""}. ${n.type === "milestone" ? "Assessment milestone." : "A learning checkpoint from your reviewed syllabus."}`,
                      })),
                    },
                  ]
                : []),
            ] satisfies RootCourse[]
          }
        />
      )}
      {(page === "Sources" || page === "Roadmap") && (
        <TutorialCourses
          key={mock ? "preview" : "live"}
          location={page === "Sources" ? "library" : "roadmap"}
          mock={mock}
          onEnrollmentChange={setTutorialEnrolled}
        />
      )}
      {page === "Roadmap" && roadmapApproved && (
        <section className="card core-panel">
          <h2>{draft?.file_name || "Your course"}</h2>
          <p>User-created · Personal syllabus and roadmap</p>
          <div className="core-actions">
            <button
              onClick={() => {
                setStage("review");
                go("Library");
              }}
            >
              Edit course syllabus
            </button>
            <button disabled={!mock} onClick={() => setRemoveCourse(true)}>
              Remove course
            </button>
          </div>
          {!mock && (
            <p>
              The API does not support removing roadmap membership while
              retaining personal course data.
            </p>
          )}
        </section>
      )}
      {removeCourse && (
        <Modal
          title={`Remove ${draft?.file_name || "your course"}?`}
          onClose={() => setRemoveCourse(false)}
        >
          <p>
            This removes this user-created course from the preview Roadmap. Its
            syllabus remains available in Courses for editing. It will not be
            added to the prepared Library catalog. No underlying course data is
            deleted.
          </p>
          <div className="core-actions">
            <button autoFocus onClick={() => setRemoveCourse(false)}>
              Cancel
            </button>
            <button
              onClick={() => {
                setRoadmapApproved(false);
                setStage("review");
                setRemoveCourse(false);
                setPlan(null);
              }}
            >
              Remove
            </button>
          </div>
        </Modal>
      )}

      {page === "Library" && (
        <div className="page-heading">
          <h1 ref={headingRef} tabIndex={-1}>
            {
              {
                upload: "Add a syllabus to your course",
                review: "Review your syllabus",
                plan: "Your learning roadmap",
                complete: "Your roadmap is ready",
              }[stage]
            }
          </h1>
        </div>
      )}
      {error && (
        <div
          role="alert"
          tabIndex={-1}
          ref={errorRef}
          className="card core-error"
        >
          {error}
        </div>
      )}
      {busy && (
        <div role="status" className="card">
          Đang xử lý…
        </div>
      )}
      {busy && page === "Library" && (
        <progress aria-label="Tiến trình xử lý đề cương" max="100" />
      )}
      {sourcePage !== null && (
        <Modal
          title={`${draft?.file_name} · tr. ${sourcePage}`}
          onClose={() => setSourcePage(null)}
        >
          <p style={{ whiteSpace: "pre-wrap" }}>
            {draft?.source_pages?.[sourcePage] ||
              "Máy chủ chưa cung cấp nội dung trang nguồn cho đề cương này."}
          </p>
          <button onClick={() => setSourcePage(null)}>Đóng</button>
        </Modal>
      )}
      {page === "Library" && stage !== "complete" && (
        <div
          className="core-setup-progress"
          aria-label="Tiến trình thiết lập môn học"
        >
          <strong>
            COURSE SETUP / STEP{" "}
            {stage === "upload" ? 1 : stage === "review" ? 2 : 3} / 3
          </strong>
          <div>
            <span className={stage === "upload" ? "active" : "finished"} />
            <span
              className={
                stage === "review"
                  ? "active"
                  : stage === "plan"
                    ? "finished"
                    : ""
              }
            />
            <span className={stage === "plan" ? "active" : ""} />
          </div>
        </div>
      )}
      {page === "Library" &&
        (stage === "upload" ? (
          <SyllabusUpload busy={busy} mock={mock} onUpload={load} />
        ) : stage === "review" ? (
          draft && (
            <SyllabusReview
              draft={draft}
              update={update}
              warnings={warnings}
              blocked={blocked}
              busy={busy}
              mock={mock}
              confirm={confirm}
              generate={generate}
              onBack={() => setStage("upload")}
              sourceChip={sourceChip}
            />
          )
        ) : stage === "complete" ? (
          <section className="card core-panel core-complete" role="status">
            <span className="core-kicker">ĐÃ HOÀN TẤT</span>
            <h2>Roadmap của bạn đã sẵn sàng</h2>
            <p>
              Bạn có thể trở về trang môn học hoặc mở lộ trình để bắt đầu học.
            </p>
            <div className="core-actions">
              <button onClick={() => setStage("upload")}>Trở về môn học</button>
              <button className="primary-action" onClick={() => go("Roadmap")}>
                Xem roadmap →
              </button>
            </div>
          </section>
        ) : null)}
      {page === "Roadmap" && !roadmapApproved && !tutorialEnrolled && (
        <section className="card core-panel">
          <h2>Chưa có roadmap được duyệt</h2>
          <p>Hoàn thành ba bước thiết lập trong tab Môn học.</p>
          <button onClick={() => go("Library")}>Mở thiết lập môn học</button>
        </section>
      )}
      {showingRoadmap && (
        <>
          <section className="card core-panel">
            <span className="core-kicker">S5 · Lộ trình</span>
            <h2>
              {stage === "plan" && page === "Library"
                ? "Duyệt roadmap được đề xuất"
                : "Roadmap theo tuần"}
            </h2>
            {page === "Library" && (
              <p className="core-warning">
                Kiểm tra thứ tự kiến thức nền, mốc kiểm tra và thời lượng trước
                khi xác nhận.
              </p>
            )}
          </section>
          {!roadmap ? (
            <section className="card core-panel">
              <h3>No roadmap yet</h3>
              <p>Xác nhận đề cương để tạo lộ trình.</p>
              <button onClick={() => go("Library")}>Mở đề cương</button>
            </section>
          ) : (
            <>
              {(roadmap.overloaded_weeks.length > 0 ||
                roadmap.nodes.some(
                  (n) =>
                    roadmap.nodes
                      .filter((x) => x.week === n.week)
                      .reduce(
                        (sum, x) =>
                          sum + (x.est_minutes ?? x.duration_minutes ?? 0),
                        0,
                      ) > weekly,
                )) && (
                <p className="card core-warning" role="alert">
                  Một số tuần vượt quỹ thời gian học. Hãy xem lại thời lượng
                  trước khi xếp lịch.
                </p>
              )}
              <div
                className="core-tabs"
                role="tablist"
                aria-label="Cách xem roadmap"
                onKeyDown={(e) => {
                  if (
                    ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
                  ) {
                    e.preventDefault();
                    const next =
                      e.key === "Home"
                        ? "timeline"
                        : e.key === "End"
                          ? "graph"
                          : roadmapTab === "timeline"
                            ? "graph"
                            : "timeline";
                    setRoadmapTab(next);
                    (
                      e.currentTarget.querySelectorAll("button")[
                        next === "timeline" ? 0 : 1
                      ] as HTMLButtonElement
                    ).focus();
                  }
                }}
              >
                <button
                  role="tab"
                  tabIndex={roadmapTab === "timeline" ? 0 : -1}
                  aria-selected={roadmapTab === "timeline"}
                  onClick={() => setRoadmapTab("timeline")}
                >
                  Theo tuần
                </button>
                <button
                  role="tab"
                  tabIndex={roadmapTab === "graph" ? 0 : -1}
                  aria-selected={roadmapTab === "graph"}
                  onClick={() => setRoadmapTab("graph")}
                >
                  Graph tiên quyết
                </button>
              </div>
              {roadmapTab === "timeline" ? (
                <RoadmapTimeline
                  roadmap={roadmap}
                  draft={draft}
                  weekly={weekly}
                  onWeeklyChange={setWeekly}
                  live={roadmapApproved && !mock}
                />
              ) : (
                <section className="card core-panel">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <h3>Knowledge Graph môn học</h3>
                  </div>
                  <GraphFilterBar
                    nodes={roadmap.nodes.map((n) => ({
                      id: n.id,
                      title: n.title,
                      type: (n.type as "topic" | "milestone") || "topic",
                      week: n.week,
                      status:
                        n.status === "done"
                          ? "mastered"
                          : n.status === "in_progress"
                            ? "in_progress"
                            : "not_started",
                    }))}
                    filters={filters}
                    onChange={setFilters}
                    onSelectNode={(nodeId) => setSelectedGraphNodeId(nodeId)}
                  />
                  {filters.viewMode === "graph" ? (
                  <div style={{ marginBottom: "16px" }}>
                    <GraphCanvas
                      nodes={filteredGraphData.nodes.map((n) => ({
                        id: n.id,
                        title: n.title,
                        type: (n.type as "topic" | "milestone") || "topic",
                        week: n.week,
                        est_minutes: n.est_minutes ?? n.duration_minutes ?? 60,
                        status:
                          n.status === "done"
                            ? "mastered"
                            : n.status === "in_progress"
                              ? "in_progress"
                              : "not_started",
                      }))}
                      edges={filteredGraphData.edges.map((e) => ({
                        parent_id: e.parent_id,
                        child_id: e.child_id,
                        kind: e.kind,
                        confidence: e.confidence,
                        origin: e.origin,
                      }))}
                      layout={graphLayoutMode}
                      onLayoutModeChange={setGraphLayoutMode}
                      selectedId={selectedGraphNodeId}
                      onSelect={setSelectedGraphNodeId}
                      onEdgeCreate={(p, c) => addEdge(p, c)}
                    />
                  </div>
                ) : (
                  <div style={{ marginBottom: "16px" }}>
                    <GraphListView
                      nodes={filteredGraphData.nodes.map((n) => ({
                        id: n.id,
                        title: n.title,
                        type: (n.type as "topic" | "milestone") || "topic",
                        week: n.week,
                        est_minutes: n.est_minutes ?? n.duration_minutes ?? 60,
                        status:
                          n.status === "done"
                            ? "mastered"
                            : n.status === "in_progress"
                              ? "in_progress"
                              : "not_started",
                      }))}
                      selectedId={selectedGraphNodeId}
                      onSelect={(id) => setSelectedGraphNodeId(id)}
                    />
                  </div>
                )}

                {selectedNodeObj && (
                  <NodePanel
                    roadmapId={roadmap.id}
                    node={selectedNodeObj}
                    allNodes={roadmap.nodes}
                    edges={roadmap.edges}
                    isOpen={Boolean(selectedNodeObj)}
                    onClose={() => setSelectedGraphNodeId(null)}
                    onSelectNode={(id) => setSelectedGraphNodeId(id)}
                  />
                )}
                  <div className="core-edges">
                    {roadmap.edges.map((e, i) => (
                      <div
                        className="core-edge"
                        key={`${e.parent_id}-${e.child_id}-${i}`}
                      >
                        <span>
                          {title(
                            roadmap.nodes.find((n) => n.id === e.parent_id),
                          )}{" "}
                          →{" "}
                          {title(
                            roadmap.nodes.find((n) => n.id === e.child_id),
                          )}
                        </span>
                        <small>
                          {e.kind} · {e.origin} ·{" "}
                          {Math.round(e.confidence * 100)}%
                        </small>
                        <button onClick={() => removeEdge(e)}>Bỏ cạnh</button>
                      </div>
                    ))}
                  </div>
                  <div className="core-row">
                    <label>
                      Học trước
                      <select
                        aria-label="Học trước"
                        value={parent}
                        onChange={(e) => setParent(e.target.value)}
                      >
                        <option value="">Chọn chặng</option>
                        {topicNodes.map((n) => (
                          <option value={n.id} key={n.id}>
                            {n.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Học sau
                      <select
                        aria-label="Học sau"
                        value={child}
                        onChange={(e) => setChild(e.target.value)}
                      >
                        <option value="">Chọn chặng</option>
                        {topicNodes.map((n) => (
                          <option value={n.id} key={n.id}>
                            {n.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button onClick={() => addEdge()}>Thêm cạnh</button>
                  </div>
                  {graphError && (
                    <p role="alert" className="core-error">
                      {graphError}
                    </p>
                  )}
                </section>
              )}
              {page === "Library" ? (
                <section className="card core-panel core-confirm-plan">
                  <p>
                    Đây là bản đề xuất. Bạn quyết định khi nào áp dụng lộ trình.
                  </p>
                  <div className="core-actions">
                    <button onClick={() => setStage("review")}>
                      ← Quay lại sửa đề cương
                    </button>
                    <button
                      className="primary-action"
                      disabled={
                        busy ||
                        !Number.isInteger(weekly) ||
                        weekly < 25 ||
                        weekly > 10080
                      }
                      onClick={approveRoadmap}
                    >
                      Xác nhận roadmap
                    </button>
                  </div>
                </section>
              ) : (
                <section className="card core-panel">
                  <h3>Xếp vào lịch</h3>
                  <p>Chọn thời gian học phù hợp trước khi tạo các buổi học.</p>
                  <button
                    className="primary-action"
                    onClick={() => setScheduleOpen(true)}
                  >
                    Xếp vào lịch
                  </button>
                </section>
              )}
            </>
          )}
          {scheduleOpen && (
            <Modal
              title="Chọn thời gian học"
              onClose={() => setScheduleOpen(false)}
            >
              <div className="core-panel">
                <div className="core-row">
                  <label>
                    Phút rảnh mỗi tuần
                    <input
                      type="number"
                      min="25"
                      value={weekly}
                      onChange={(e) => setWeekly(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Tối đa phút mỗi ngày
                    <input
                      type="number"
                      min="25"
                      max="1440"
                      value={daily}
                      onChange={(e) => setDaily(Number(e.target.value))}
                    />
                  </label>
                </div>
                <div className="core-actions">
                  <button onClick={() => setScheduleOpen(false)}>Hủy</button>
                  <button
                    className="primary-action"
                    disabled={
                      busy ||
                      !Number.isInteger(weekly) ||
                      weekly < 25 ||
                      weekly > 10080 ||
                      !Number.isInteger(daily) ||
                      daily < 25 ||
                      daily > 1440
                    }
                    onClick={schedule}
                  >
                    Tạo lịch học
                  </button>
                </div>
              </div>
            </Modal>
          )}
        </>
      )}
      {/* Live mode shows the real calendar (Workspace) instead. */}
      {page === "Schedule" && plan && (
        <section className="card core-panel">
          <h2>{mock ? "S7 · Lịch học" : "New roadmap sessions"}</h2>
          {!!plan?.unscheduled?.length && (
            <p role="alert">
              {plan.unscheduled.length} chặng chưa xếp được. Tuần quá tải:{" "}
              {plan.overloaded_weeks?.join(", ") ||
                "Hãy tăng thời gian học hoặc kiểm tra giờ rảnh."}
            </p>
          )}
          {plan?.sessions.length ? (
            <ul className="core-sessions">
              {plan.sessions.map((s) => (
                <li key={s.id}>
                  <strong>{s.title}</strong>
                  <span>{new Date(s.starts_at).toLocaleString("vi-VN")}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>Xếp roadmap vào lịch để xem buổi học.</p>
          )}
        </section>
      )}
    </div>
  );
}
