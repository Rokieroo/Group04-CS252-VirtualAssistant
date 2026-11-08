import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { InsufficientSourcesNotice, VerifiedSourceCard } from "../../components/VerifiedSourceCard";
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
 * Each resource uses the VerifiedSourceCard the graph node panel shares (#104).
 */
export function NodeMaterials({ nodeId }: { nodeId: string }) {
  const [files, setFiles] = useState<MaterialFile[]>([]);
  const [found, setFound] = useState<NodeResources | null>(null);
  const [filter, setFilter] = useState("all");
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
        <>
          <InsufficientSourcesNotice />
          {found.gaps.length > 0 && <p className="sm muted">{found.gaps.join("; ")}</p>}
        </>
      )}

      {found.status === "ready" && shown.length > 0 && (
        <ul className="core-catalog-sources-list">
          {shown.map((s) => (
            <li key={s.id}>
              {/* /resources returns only sources that passed vetting (spec 8.6). */}
              <VerifiedSourceCard
                source={{ ...s, verification_status: "verified" }}
                onFeedback={(helpful) => void rate(s, helpful)}
                actions={
                  s.id in feedback ? (
                    <span className="core-feedback-ack">✓ Cảm ơn đánh giá!</span>
                  ) : undefined
                }
              />
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
