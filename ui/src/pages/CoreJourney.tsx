import { RoadmapTimeline } from "./course-setup/RoadmapTimeline";
import { SyllabusUpload } from "./course-setup/SyllabusUpload";
import { SyllabusReview } from "./course-setup/SyllabusReview";
import { Modal } from "../components/Modal";
import { useState } from "react";
import type { Page } from "../navigation";
import type { RoadmapNode } from "../api/types";
import { BackendError } from "../api/backend";
import {
  createsRoadmapCycle,
  liveCoreService,
  mockCoreService,
  previewRoadmap,
  uploadError,
  warningsFor,
  type CoreService,
  type Edge,
  type SyllabusDraft,
  type RoadmapDraft,
} from "../api/core";
import "./core-journey.css";

const title = (node: RoadmapNode | undefined) =>
  node?.title || "Chặng chưa xác định";
const uiError = (error: unknown) => {
  if (error instanceof BackendError)
    return (
      (
        {
          invalid_file: "Tệp không hợp lệ hoặc bị hỏng.",
          file_too_large: "Tệp lớn hơn 20 MB.",
          unsupported_type: "Chỉ hỗ trợ PDF hoặc DOCX.",
          not_a_syllabus: "Tệp này không giống đề cương môn học.",
          has_blocking_warnings: "Hãy sửa các cảnh báo trước khi xác nhận.",
        } as Record<string, string>
      )[error.code] || error.message
    );
  return error instanceof Error ? error.message : "Có lỗi xảy ra. Hãy thử lại.";
};
export function CoreJourney({
  page,
  go,
  mock = false,
}: {
  page: Page;
  go: (p: Page) => void;
  mock?: boolean;
}) {
  const service: CoreService = mock ? mockCoreService : liveCoreService;
  const [draft, setDraft] = useState<SyllabusDraft | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapDraft | null>(null);
  const [stage, setStage] = useState<"upload" | "review" | "plan" | "complete">(
    "upload",
  );
  const [roadmapApproved, setRoadmapApproved] = useState(false);
  const [roadmapTab, setRoadmapTab] = useState<"timeline" | "graph">(
    "timeline",
  );
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [parent, setParent] = useState("");
  const [child, setChild] = useState("");
  const [graphError, setGraphError] = useState("");
  const [weekly, setWeekly] = useState(300);
  const [daily, setDaily] = useState(120);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [plan, setPlan] = useState<{
    sessions: { id: string; title: string; starts_at: string }[];
  } | null>(null);
  const [sourcePage, setSourcePage] = useState<number | null>(null);
  const warnings = draft ? [...draft.warnings, ...warningsFor(draft)] : [];
  const blocked = warnings.some((w) => w.blocking);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(uiError(e));
    } finally {
      setBusy(false);
    }
  };
  const load = (file: File | string) => {
    if (file instanceof File) {
      const issue = uploadError(file);
      if (issue) {
        setError(issue);
        return;
      }
    }
    setProgress(10);
    void run(async () => {
      const result = await service.upload(file);
      setProgress(100);
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
      setRoadmap(
        mock ? await service.generate(draft.id) : previewRoadmap(draft),
      );
      setStage("plan");
    });
  };
  const approveRoadmap = () => {
    if (!draft || weekly < 25 || weekly > 10080) return;
    void run(async () => {
      if (!mock) setRoadmap(await service.generate(draft.id));
      setRoadmapApproved(true);
      setStage("complete");
    });
  };
  const addEdge = () => {
    if (!roadmap || !parent || !child) return;
    if (createsRoadmapCycle(roadmap.edges, parent, child)) {
      setGraphError("Tạo vòng lặp, hãy bỏ một cạnh.");
      return;
    }
    setGraphError("");
    if (
      !roadmap.edges.some((e) => e.parent_id === parent && e.child_id === child)
    )
      setRoadmap({
        ...roadmap,
        edges: [
          ...roadmap.edges,
          {
            parent_id: parent,
            child_id: child,
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
    if (!roadmap) return;
    void run(async () => {
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
      {page === "Library" && (
        <div className="page-heading">
          <h1>
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
        <div role="alert" className="card core-error">
          {error}
        </div>
      )}
      {busy && (
        <div role="status" className="card">
          Đang xử lý…
        </div>
      )}
      {busy && page === "Library" && (
        <progress
          aria-label="Tiến trình xử lý đề cương"
          max="100"
          value={progress}
        />
      )}
      {sourcePage !== null && (
        <Modal
          title={`${draft?.file_name} · tr. ${sourcePage}`}
          onClose={() => setSourcePage(null)}
        >
          <p>
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
      {page === "Roadmap" && !roadmapApproved && (
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
              {roadmap.overloaded_weeks.length > 0 && (
                <p className="card core-warning" role="alert">
                  Tuần {roadmap.overloaded_weeks.join(", ")} quá tải. Hãy xem
                  lại thời lượng trước khi xếp lịch.
                </p>
              )}
              <div
                className="core-tabs"
                role="tablist"
                aria-label="Cách xem roadmap"
              >
                <button
                  role="tab"
                  aria-selected={roadmapTab === "timeline"}
                  onClick={() => setRoadmapTab("timeline")}
                >
                  Theo tuần
                </button>
                <button
                  role="tab"
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
                />
              ) : (
                <section className="card core-panel">
                  <h3>Quan hệ tiên quyết</h3>
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
                    <button onClick={addEdge}>Thêm cạnh</button>
                  </div>
                  {graphError && (
                    <p role="alert" className="core-error">
                      {graphError}
                    </p>
                  )}
                  {!mock && (
                    <p className="hint">
                      Máy chủ chưa lưu cạnh prerequisite; thay đổi graph chỉ có
                      hiệu lực trong phiên này.
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
                      disabled={busy || weekly < 25 || weekly > 10080}
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
                    disabled={busy || weekly < 25 || daily < 25 || daily > 1440}
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
      {page === "Schedule" && (
        <section className="card core-panel">
          <h2>S7 · Lịch học</h2>
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
      {page === "Sources" && (
        <section className="card core-panel">
          <h2>S8 · Thư viện nguồn</h2>
          <p>Chưa có nguồn học đã lưu.</p>
        </section>
      )}
    </div>
  );
}
