import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { decideMaterial, nodeMaterials, pageRanges, type MaterialFile } from "../../api/materials";
import {
  fetchNodeResources,
  searchNodeResources,
  sendResourceFeedback,
} from "../../api/resources";
import type { NodeResources, Resource } from "../../api/types";

// Spec 8.6 format filters; "read" groups every text format.
const FILTERS: { id: string; label: string; formats?: Resource["format"][] }[] = [
  { id: "all", label: "Tất cả" },
  { id: "video", label: "Video", formats: ["video"] },
  { id: "read", label: "Bài viết / Đọc", formats: ["article", "book", "paper"] },
  { id: "exercise", label: "Bài tập", formats: ["exercise"] },
];
const POLL_MS = 3000;

/**
 * S6 sources of one roadmap node (spec 8.6, 8.7, 12.1; #58, #114): the learner's own
 * pages first, then verified resources with filters, one-tap feedback and "Tìm lại".
 */
export function NodeMaterials({ nodeId }: { nodeId: string }) {
  const [files, setFiles] = useState<MaterialFile[]>([]);
  const [found, setFound] = useState<NodeResources | null>(null);
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [materials, resources] = await Promise.all([
        nodeMaterials(nodeId),
        fetchNodeResources(nodeId),
      ]);
      setFiles(materials);
      setFound(resources);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load learning sources.");
    }
  }, [nodeId]);

  useEffect(() => {
    void load();
  }, [load]);

  // The search runs as a background job; the server answers "searching" until it ends.
  useEffect(() => {
    if (found?.status !== "searching") return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [found?.status, load]);

  const act = async (work: () => Promise<void>, failure: string) => {
    setBusy(true);
    try {
      await work();
    } catch (err) {
      setError(err instanceof Error ? err.message : failure);
    } finally {
      setBusy(false);
    }
  };

  const decide = (file: MaterialFile, attached: boolean) =>
    act(async () => {
      await decideMaterial(nodeId, file, attached);
      await load();
    }, "Could not save your answer.");

  const searchAgain = () =>
    act(async () => {
      await searchNodeResources(nodeId);
      await load();
    }, "Could not start a new search.");

  const rate = (resource: Resource, helpful: boolean) =>
    act(async () => {
      const { replacement } = await sendResourceFeedback(resource.id, { node_id: nodeId, helpful });
      setFeedback((prev) => ({ ...prev, [resource.id]: helpful }));
      if (!helpful && replacement)
        setFound((prev) =>
          prev && {
            ...prev,
            resources: prev.resources.map((r) => (r.id === resource.id ? replacement : r)),
          },
        );
    }, "Could not save feedback.");

  if (error) return <p role="alert" className="row-error">{error}</p>;
  if (!found) return <p className="core-field-label">Loading sources…</p>;

  const attached = files.filter((f) => f.status === "attached");
  const suggested = files.filter((f) => f.status === "suggested");
  const formats = FILTERS.find((f) => f.id === filter)?.formats;
  const shown = found.resources.filter((r) => !formats || formats.includes(r.format));

  return (
    <div className="core-node-sources" aria-label="Learning sources">
      {attached.length > 0 && (
        <div className="core-own-material-section">
          <h4 className="core-sources-heading">Tài liệu cá nhân của bạn</h4>
          <ul className="core-own-material">
            {attached.map((f) => (
              <li key={f.file_name}>
                <span className="core-own-badge">Tài liệu của bạn</span>
                <strong>{f.file_name}</strong>
                <span> · trang {pageRanges(f.pages.map((p) => p.page))}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {suggested.map((file) => (
        <div className="core-material-suggestion" key={file.file_name}>
          <p>
            Có phải <strong>{file.file_name}</strong> (trang{" "}
            {pageRanges(file.pages.map((p) => p.page))}) thuộc nội dung chặng này?
          </p>
          <Button primary disabled={busy} onClick={() => void decide(file, true)}>
            Đính kèm chặng này
          </Button>
          <Button disabled={busy} onClick={() => void decide(file, false)}>
            Bỏ qua
          </Button>
        </div>
      ))}

      <div className="core-source-toolbar">
        <div className="core-format-filters" role="group" aria-label="Lọc theo định dạng">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`core-filter-btn ${filter === f.id ? "active" : ""}`}
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
            >
              {f.id === "all" ? `${f.label} (${found.resources.length})` : f.label}
            </button>
          ))}
        </div>
        <Button disabled={busy || found.status === "searching"} onClick={() => void searchAgain()}>
          Tìm lại
        </Button>
      </div>

      {found.status === "searching" && (
        <div className="core-searching-box" role="status">
          <p className="core-field-label">Đang tìm kiếm nguồn học chất lượng cao…</p>
        </div>
      )}

      {found.status === "insufficient" && (
        <div className="core-insufficient-sources" role="status">
          <p className="core-insufficient-title">
            <strong>Chưa tìm được nguồn đủ tốt</strong>
          </p>
          <p className="sm muted">
            Các nguồn tìm được chưa đạt ngưỡng chất lượng thẩm định ≥ 0.65 theo 7 tiêu chí.
            {found.gaps.length > 0 && ` (${found.gaps.join("; ")})`}
          </p>
        </div>
      )}

      {found.status === "ready" && shown.length > 0 && (
        <ul className="core-catalog-sources-list">
          {shown.map((s) => (
            <li className="core-resource-card" key={s.id}>
              <div className="core-resource-header">
                <div className="core-resource-title-row">
                  <span className="core-verified-badge">✓ Đã xác minh</span>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="core-resource-title">
                    {s.title} ↗
                  </a>
                </div>
                <div className="core-resource-meta-row">
                  <span className="core-real-domain">{s.domain}</span>
                  {s.duration_min ? <span> · {s.duration_min} phút</span> : null}
                  <span> · {s.format}</span>
                  <button
                    type="button"
                    className="core-score-badge-btn"
                    aria-expanded={expanded === s.id}
                    onClick={() => setExpanded(expanded === s.id ? null : s.id)}
                  >
                    ★ {Math.round(s.score * 100)}% (7 tiêu chí)
                  </button>
                </div>
              </div>

              {s.reason && <p className="core-resource-reason">{s.reason}</p>}
              {s.evidence_quote && (
                <blockquote className="core-evidence-quote">“{s.evidence_quote}”</blockquote>
              )}

              {expanded === s.id && (
                <div className="core-rubric-breakdown">
                  <h5>Chi tiết 7 tiêu chí thẩm định chất lượng (Spec 11.4):</h5>
                  <div className="core-rubric-grid">
                    {Object.entries(s.breakdown).map(([k, v]) => (
                      <div className="core-rubric-item" key={k}>
                        <span className="core-rubric-key">{k}</span>
                        <span className="core-rubric-val">{Math.round(v * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="core-feedback-bar">
                <span className="core-feedback-label">Nguồn này có hữu ích?</span>
                <button
                  type="button"
                  className={`core-feedback-btn ${feedback[s.id] === true ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => void rate(s, true)}
                >
                  👍 Hữu ích
                </button>
                <button
                  type="button"
                  className={`core-feedback-btn ${feedback[s.id] === false ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => void rate(s, false)}
                >
                  👎 Không phù hợp
                </button>
                {s.id in feedback && <span className="core-feedback-ack">✓ Cảm ơn đánh giá!</span>}
              </div>
            </li>
          ))}
        </ul>
      )}

      {found.status === "ready" && found.resources.length === 0 && (
        <p className="core-field-label">Chưa có nguồn cho chặng này.</p>
      )}
    </div>
  );
}
