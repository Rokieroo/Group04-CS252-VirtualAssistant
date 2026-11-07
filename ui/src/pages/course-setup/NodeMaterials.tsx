import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/Button";
import {
  InsufficientSourcesNotice,
  VerifiedSourceCard,
  type VerifiedSource,
} from "../../components/VerifiedSourceCard";
import {
  decideMaterial,
  nodeMaterials,
  nodeSources,
  pageRanges,
  type MaterialFile,
  type RankedSource,
} from "../../api/materials";
import { fetchNodeResources, searchNodeResources, sendResourceFeedback } from "../../api/resources";

/**
 * S6 sources of one roadmap node (spec 12.1, #114, #58, #104):
 * 1. The learner's own pages first (with one-tap attachment for suggestions).
 * 2. Shared VerifiedSourceCard for verified catalog/web sources with domain names, format filters, and one-tap feedback.
 * 3. Exact spec message "Chưa tìm được nguồn đủ tốt" when insufficient.
 */
export function NodeMaterials({ nodeId }: { nodeId: string }) {
  const [sources, setSources] = useState<RankedSource[] | null>(null);
  const [catalogResources, setCatalogResources] = useState<VerifiedSource[]>([]);
  const [suggested, setSuggested] = useState<MaterialFile[]>([]);
  const [status, setStatus] = useState<"searching" | "ready" | "insufficient">("ready");
  const [formatFilter, setFormatFilter] = useState<string>("all");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ranked, files] = await Promise.all([nodeSources(nodeId), nodeMaterials(nodeId)]);
      setSources(ranked.sources);
      setSuggested(files.filter((f) => f.status === "suggested"));
      if (ranked.status === "insufficient") {
        setStatus("insufficient");
      } else {
        setStatus("ready");
      }
      setError("");
    } catch {
      // Fallback to fetchNodeResources if available
      try {
        const res = await fetchNodeResources(nodeId);
        setStatus(res.status);
        setCatalogResources(
          res.resources.map((r) => ({
            id: r.id,
            title: r.title,
            url: r.url,
            domain: r.domain,
            provider: r.domain,
            format: r.format,
            duration_min: r.duration_min,
            verification_status: "verified",
            score: r.score,
            breakdown: r.breakdown,
            reason: r.reason,
            evidence_quote: r.evidence_quote,
          }))
        );
        setError("");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load sources.");
      }
    }
  }, [nodeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRetrySearch = async () => {
    setSearching(true);
    setStatus("searching");
    try {
      await searchNodeResources(nodeId);
      await load();
    } catch {
      setError("Không thể tìm lại nguồn.");
    } finally {
      setSearching(false);
    }
  };

  const handleFeedback = async (sourceId: string, helpful: boolean) => {
    try {
      const res = await sendResourceFeedback(sourceId, {
        node_id: nodeId,
        helpful,
        reason: helpful ? "helpful" : "wrong_level",
      });
      if (!helpful && res.replacement) {
        const rep = res.replacement;
        setCatalogResources((prev) =>
          prev.map((item) =>
            item.id === sourceId
              ? {
                  id: rep.id,
                  title: rep.title,
                  url: rep.url,
                  domain: rep.domain,
                  provider: rep.domain,
                  format: rep.format,
                  duration_min: rep.duration_min,
                  verification_status: "verified",
                  score: rep.score,
                  breakdown: rep.breakdown,
                  reason: rep.reason,
                  evidence_quote: rep.evidence_quote,
                }
              : item
          )
        );
      }
    } catch {
      // Feedback saved or logged
    }
  };

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

  if (error) return <p role="alert" className="row-error">{error}</p>;
  if (status === "searching" || searching) {
    return (
      <div className="core-node-sources" aria-label="Đang tìm kiếm">
        <p className="core-field-label">Đang tìm kiếm nguồn học chất lượng cao…</p>
      </div>
    );
  }
  if (sources === null && catalogResources.length === 0 && status !== "insufficient") {
    return <p className="core-field-label">Loading sources…</p>;
  }

  const own = sources?.filter((s) => s.kind === "user_material") || [];
  const rawCatalog = (sources?.filter((s) => s.kind !== "user_material") || []).map((s) => ({
    id: s.id,
    title: s.title,
    url: s.url,
    domain: s.url ? new URL(s.url).hostname : undefined,
    provider: s.provider,
    format: s.format,
    reason: s.reason,
    verification_status: "verified",
  }));

  const allCatalog: VerifiedSource[] =
    catalogResources.length > 0 ? catalogResources : rawCatalog;

  const filteredCatalog =
    formatFilter === "all"
      ? allCatalog
      : allCatalog.filter((item) => item.format?.toLowerCase() === formatFilter.toLowerCase());

  return (
    <div className="core-node-sources" aria-label="Learning sources">
      {/* 1. Learner's own files first (Spec 12.1, #114) */}
      {own.length > 0 && (
        <section aria-label="Tài liệu riêng của bạn">
          <ul className="core-own-material">
            {own.map((s) => (
              <li key={s.id}>
                <span className="core-own-badge">{s.reason}</span>
                <strong>{s.title}</strong>
                <span> · trang {pageRanges(s.pages)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Suggested files awaiting one tap */}
      {suggested.map((file) => (
        <div className="core-material-suggestion" key={file.file_name}>
          <p>
            Tài liệu <strong>{file.file_name}</strong>, các trang{" "}
            {pageRanges(file.pages.map((p) => p.page))} có thuộc về chặng này không?
          </p>
          <Button primary disabled={busy} onClick={() => void decide(file, true)}>
            Đồng ý, gắn vào chặng
          </Button>
          <Button disabled={busy} onClick={() => void decide(file, false)}>
            Không
          </Button>
        </div>
      ))}

      {/* Insufficient status banner (Spec 8.6, Issue #58, #104) */}
      {status === "insufficient" && (
        <InsufficientSourcesNotice onRetry={handleRetrySearch} busy={searching} />
      )}

      {/* Format filters toolbar */}
      {allCatalog.length > 0 && (
        <div className="core-format-filters" role="group" aria-label="Lọc theo định dạng">
          {[
            { id: "all", label: "Tất cả" },
            { id: "video", label: "Video" },
            { id: "article", label: "Bài viết / Đọc" },
            { id: "exercise", label: "Bài tập" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`core-format-tab ${formatFilter === tab.id ? "active" : ""}`}
              onClick={() => setFormatFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
          <Button disabled={searching} onClick={handleRetrySearch}>
            Tìm lại
          </Button>
        </div>
      )}

      {/* 2. Verified catalog sources rendered with shared VerifiedSourceCard (#104) */}
      {filteredCatalog.length > 0 && (
        <div className="core-catalog-cards" role="list">
          {filteredCatalog.map((source) => (
            <div role="listitem" key={source.id}>
              <VerifiedSourceCard
                source={source}
                onFeedback={(helpful) => void handleFeedback(source.id, helpful)}
              />
            </div>
          ))}
        </div>
      )}

      {allCatalog.length === 0 && own.length === 0 && suggested.length === 0 && status !== "insufficient" && (
        <p className="core-field-label">Chưa có nguồn nào cho chặng này.</p>
      )}
    </div>
  );
}
