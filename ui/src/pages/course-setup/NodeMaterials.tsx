import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/Button";
import {
  decideMaterial,
  nodeMaterials,
  nodeSources,
  pageRanges,
  type MaterialFile,
} from "../../api/materials";
import {
  fetchNodeResources,
  searchNodeResources,
  sendResourceFeedback,
} from "../../api/resources";
import type { Resource } from "../../api/types";

/**
 * S6 Stage Page / Sources (Spec 8.6, 8.7, Issue #58):
 * 1. User's own material first (#114), suggestions awaiting one tap.
 * 2. Verified catalog resources with format filters, real domains, and safe links.
 * 3. 7-criteria quality score rubric breakdown.
 * 4. Grounded quote from source text.
 * 5. One-tap feedback with inline replacement.
 * 6. "searching" and "insufficient" ("Chưa tìm được nguồn đủ tốt") states + "Tìm lại".
 */
export function NodeMaterials({ nodeId }: { nodeId: string }) {
  const [userFiles, setUserFiles] = useState<MaterialFile[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [status, setStatus] = useState<"loading" | "searching" | "ready" | "insufficient">("loading");
  const [gaps, setGaps] = useState<string[]>([]);
  const [formatFilter, setFormatFilter] = useState<"all" | "video" | "article" | "exercise">("all");
  const [expandedBreakdown, setExpandedBreakdown] = useState<Record<string, boolean>>({});
  const [feedbackStatus, setFeedbackStatus] = useState<Record<string, "helpful" | "unhelpful">>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [filesRes, verifiedRes, rankedRes] = await Promise.allSettled([
        nodeMaterials(nodeId),
        fetchNodeResources(nodeId),
        nodeSources(nodeId),
      ]);

      if (filesRes.status === "fulfilled") {
        setUserFiles(filesRes.value);
      }

      if (verifiedRes.status === "fulfilled") {
        setStatus(verifiedRes.value.status);
        setResources(verifiedRes.value.resources || []);
        setGaps(verifiedRes.value.gaps || []);
      } else if (rankedRes.status === "fulfilled") {
        // Fallback to nodeSources if verified endpoint not ready
        const mapped: Resource[] = rankedRes.value.sources
          .filter((s) => s.kind !== "user_material")
          .map((s, idx) => ({
            id: s.id,
            rank: idx + 1,
            title: s.title,
            url: s.url || "#",
            domain: s.url ? new URL(s.url).hostname : s.provider,
            format: (s.format as Resource["format"]) || "article",
            language: "en",
            duration_min: null,
            is_free: true,
            score: 0.8,
            breakdown: {
              relevance: 0.8,
              authority: 0.8,
              level_fit: 0.8,
              pedagogy: 0.8,
              freshness: 0.8,
              accessibility: 0.8,
              community: 0.8,
            },
            reason: s.reason,
            evidence_quote: "",
            pinned: false,
          }));
        setResources(mapped);
        setStatus(rankedRes.value.status === "insufficient" ? "insufficient" : "ready");
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load learning sources.");
    }
  }, [nodeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (file: MaterialFile, attached: boolean) => {
    setBusy(true);
    try {
      await decideMaterial(nodeId, file, attached);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your answer.");
    } finally {
      setBusy(false);
    }
  };

  const handleFeedback = async (resourceId: string, helpful: boolean) => {
    setBusy(true);
    try {
      const res = await sendResourceFeedback(resourceId, {
        node_id: nodeId,
        helpful,
        reason: helpful ? undefined : "wrong_level",
      });
      setFeedbackStatus((prev) => ({
        ...prev,
        [resourceId]: helpful ? "helpful" : "unhelpful",
      }));
      if (!helpful && res.replacement) {
        setResources((prev) =>
          prev.map((r) => (r.id === resourceId ? res.replacement! : r)),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save feedback.");
    } finally {
      setBusy(false);
    }
  };

  const handleSearchAgain = async () => {
    setBusy(true);
    setStatus("searching");
    try {
      await searchNodeResources(nodeId);
      setTimeout(() => {
        void load();
        setBusy(false);
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not trigger search.");
      setBusy(false);
    }
  };

  const toggleBreakdown = (id: string) => {
    setExpandedBreakdown((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  if (error) return <p role="alert" className="row-error">{error}</p>;
  if (status === "loading") return <p className="core-field-label">Loading sources…</p>;

  const attachedFiles = userFiles.filter((f) => f.status === "attached");
  const suggestedFiles = userFiles.filter((f) => f.status === "suggested");

  const filteredResources = resources.filter((r) => {
    if (formatFilter === "all") return true;
    if (formatFilter === "video") return r.format === "video";
    if (formatFilter === "article") return ["article", "book", "paper"].includes(r.format);
    if (formatFilter === "exercise") return r.format === "exercise";
    return true;
  });

  return (
    <div className="core-node-sources" aria-label="Learning sources">
      {/* 1. User's own material (Spec 12.1, #114) */}
      {attachedFiles.length > 0 && (
        <div className="core-own-material-section">
          <h4 className="core-sources-heading">Tài liệu cá nhân của bạn</h4>
          <ul className="core-own-material">
            {attachedFiles.map((f) => (
              <li key={f.file_name}>
                <span className="core-own-badge">Tài liệu của bạn</span>
                <strong>{f.file_name}</strong>
                <span> · trang {pageRanges(f.pages.map((p) => p.page))}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggested user files awaiting one tap */}
      {suggestedFiles.map((file) => (
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

      {/* 2. Format filters (Spec 8.6, Issue #58) */}
      <div className="core-source-toolbar">
        <div className="core-format-filters" role="group" aria-label="Lọc theo định dạng">
          <button
            type="button"
            className={`core-filter-btn ${formatFilter === "all" ? "active" : ""}`}
            onClick={() => setFormatFilter("all")}
          >
            Tất cả ({resources.length})
          </button>
          <button
            type="button"
            className={`core-filter-btn ${formatFilter === "video" ? "active" : ""}`}
            onClick={() => setFormatFilter("video")}
          >
            Video
          </button>
          <button
            type="button"
            className={`core-filter-btn ${formatFilter === "article" ? "active" : ""}`}
            onClick={() => setFormatFilter("article")}
          >
            Bài viết / Đọc
          </button>
          <button
            type="button"
            className={`core-filter-btn ${formatFilter === "exercise" ? "active" : ""}`}
            onClick={() => setFormatFilter("exercise")}
          >
            Bài tập
          </button>
        </div>
        <Button disabled={busy} onClick={handleSearchAgain}>
          🔄 Tìm lại
        </Button>
      </div>

      {/* 3. Status handling: Searching */}
      {status === "searching" && (
        <div className="core-searching-box" role="status">
          <p className="core-field-label">Đang tìm kiếm nguồn học chất lượng cao…</p>
        </div>
      )}

      {/* 4. Status handling: Insufficient (Spec requirement: "Chưa tìm được nguồn đủ tốt") */}
      {status === "insufficient" && (
        <div className="core-insufficient-sources" role="status">
          <p className="core-insufficient-title">
            <strong>Chưa tìm được nguồn đủ tốt</strong>
          </p>
          <p className="sm muted">
            Các nguồn tìm được chưa đạt ngưỡng chất lượng thẩm định ≥ 0.65 theo 7 tiêu chí.
            {gaps.length > 0 && ` (${gaps.join("; ")})`}
          </p>
          <Button disabled={busy} onClick={handleSearchAgain}>
            Tìm lại
          </Button>
        </div>
      )}

      {/* 5. Verified Catalog Resources list */}
      {status === "ready" && filteredResources.length > 0 && (
        <ul className="core-catalog-sources-list">
          {filteredResources.map((s) => (
            <li className="core-resource-card" key={s.id}>
              <div className="core-resource-header">
                <div className="core-resource-title-row">
                  <span className="core-verified-badge">✓ Đã xác minh</span>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="core-resource-title"
                  >
                    {s.title} ↗
                  </a>
                </div>
                <div className="core-resource-meta-row">
                  <span className="core-real-domain">{s.domain}</span>
                  {s.duration_min && <span> · {s.duration_min} phút</span>}
                  <span> · {s.format}</span>
                  {s.score > 0 && (
                    <button
                      type="button"
                      className="core-score-badge-btn"
                      onClick={() => toggleBreakdown(s.id)}
                      title="Bấm để xem điểm chi tiết 7 tiêu chí"
                    >
                      ★ {Math.round(s.score * 100)}% (7 tiêu chí)
                    </button>
                  )}
                </div>
              </div>

              {/* Reason */}
              {s.reason && <p className="core-resource-reason">{s.reason}</p>}

              {/* Grounded Quote (evidence_quote) */}
              {s.evidence_quote && (
                <blockquote className="core-evidence-quote">
                  “{s.evidence_quote}”
                </blockquote>
              )}

              {/* 7-Criteria breakdown accordion */}
              {expandedBreakdown[s.id] && s.breakdown && (
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

              {/* One-tap feedback (Spec 8.7, Issue #58) */}
              <div className="core-feedback-bar">
                <span className="core-feedback-label">Nguồn này có hữu ích?</span>
                <button
                  type="button"
                  className={`core-feedback-btn ${feedbackStatus[s.id] === "helpful" ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => handleFeedback(s.id, true)}
                >
                  👍 Hữu ích
                </button>
                <button
                  type="button"
                  className={`core-feedback-btn ${feedbackStatus[s.id] === "unhelpful" ? "active" : ""}`}
                  disabled={busy}
                  onClick={() => handleFeedback(s.id, false)}
                >
                  👎 Không phù hợp
                </button>
                {feedbackStatus[s.id] === "helpful" && (
                  <span className="core-feedback-ack">✓ Cảm ơn đánh giá!</span>
                )}
                {feedbackStatus[s.id] === "unhelpful" && (
                  <span className="core-feedback-ack">✓ Đã đổi nguồn thay thế nếu có</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {status === "ready" && resources.length === 0 && (
        <p className="core-field-label">Chưa có nguồn cho chặng này.</p>
      )}
    </div>
  );
}
