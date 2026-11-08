import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchCatalogReviewQueue,
  rejectCatalogResource,
  verifyCatalogResource,
  type CatalogReviewItem,
} from "../api/catalog";
import "./AdminCatalogPage.css";

const PRESET_VERIFY_REASONS = [
  "Footer confirms CC-BY-4.0",
  "Verified OER educational source",
  "Legitimate university publication",
  "Public domain academic notes",
];

const PRESET_REJECT_REASONS = [
  "takedown",
  "paywalled / login required",
  "pirated or unauthorized mirror",
  "broken link / 404",
];

// Must match `licenses` in data/policy/catalog_sources.yaml: verify rejects any other.
const LICENSES = [
  "CC-BY-3.0",
  "CC-BY-4.0",
  "CC-BY-SA-4.0",
  "CC-BY-NC-SA-3.0",
  "CC-BY-NC-SA-4.0",
  "CC0-1.0",
  "VN-LEGAL-TEXT",
  "ALL-RIGHTS-RESERVED",
];

export function AdminCatalogPage() {
  const [items, setItems] = useState<CatalogReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Filters
  const [providerFilter, setProviderFilter] = useState("all");
  const [reasonFilter, setReasonFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  // Review inspector state
  // Licenses the admin picked, per resource; otherwise the one the checks found.
  const [licenseChoice, setLicenseChoice] = useState<Record<string, string>>({});
  const [customReason, setCustomReason] = useState(PRESET_VERIFY_REASONS[0]);
  const [rejectReason, setRejectReason] = useState(PRESET_REJECT_REASONS[0]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Productivity metrics (Acceptance criteria: 20 sources in < 5 mins)
  const [reviewedCount, setReviewedCount] = useState(0);
  const [startTime] = useState<number>(() => Date.now());
  const [elapsedSecs, setElapsedSecs] = useState(0);

  // Timer for measuring review speed
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSecs(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [startTime]);

  // Load items
  const loadQueue = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchCatalogReviewQueue(100);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the review queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  // Filter items
  const filteredItems = items.filter((item) => {
    if (providerFilter !== "all" && item.provider !== providerFilter) return false;
    if (reasonFilter !== "all") {
      const hasReason = item.checks.some((c) => c.reason.includes(reasonFilter));
      if (!hasReason) return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const match =
        item.title.toLowerCase().includes(term) ||
        (item.url && item.url.toLowerCase().includes(term)) ||
        item.provider.toLowerCase().includes(term);
      if (!match) return false;
    }
    return true;
  });

  const selectedItem =
    filteredItems.length > 0
      ? filteredItems[Math.min(selectedIndex, filteredItems.length - 1)]
      : null;

  const license = selectedItem ? (licenseChoice[selectedItem.id] ?? selectedItem.license ?? "") : "";

  // Refs for keyboard handlers to access current state without recreating listeners
  const selectedItemRef = useRef(selectedItem);
  selectedItemRef.current = selectedItem;
  const filteredLengthRef = useRef(filteredItems.length);
  filteredLengthRef.current = filteredItems.length;
  const licenseRef = useRef(license);
  licenseRef.current = license;
  const customReasonRef = useRef(customReason);
  customReasonRef.current = customReason;
  const rejectReasonRef = useRef(rejectReason);
  rejectReasonRef.current = rejectReason;
  const busyRef = useRef(busy);
  busyRef.current = busy;

  // Actions
  const decide = async (item: CatalogReviewItem, request: () => Promise<unknown>, done: string) => {
    if (busyRef.current) return;
    setBusy(true);
    busyRef.current = true;
    try {
      await request();
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      setReviewedCount((c) => c + 1);
      setToast(done);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The decision was not saved.");
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const handleVerify = async (item = selectedItemRef.current) => {
    if (!item) return;
    const chosen = licenseRef.current || null;
    await decide(
      item,
      () => verifyCatalogResource(item.id, customReasonRef.current, chosen),
      `✓ Đã duyệt: "${item.title}"${chosen ? ` (${chosen})` : ""}`,
    );
  };

  const handleReject = async (item = selectedItemRef.current) => {
    if (!item) return;
    const reason = rejectReasonRef.current;
    await decide(
      item,
      () => rejectCatalogResource(item.id, reason),
      `✗ Đã loại: "${item.title}" (Lý do: ${reason})`,
    );
  };

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  // Keyboard navigation & shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts when typing inside form inputs
      const target = e.target as HTMLElement;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT")
      ) {
        return;
      }

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, Math.max(0, filteredLengthRef.current - 1)));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "v" || e.key === "V") {
        e.preventDefault();
        void handleVerify();
      } else if (e.key === "r" || e.key === "x" || e.key === "R" || e.key === "X") {
        e.preventDefault();
        void handleReject();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const providers = Array.from(new Set(items.map((i) => i.provider))).filter(Boolean);

  return (
    <div className="admin-catalog-page" aria-label="Admin Catalog Review Queue">
      {/* Header */}
      <header className="acp-header">
        <div className="acp-title-area">
          <h2>Hàng chờ duyệt nguồn Catalog (Catalog Review Queue)</h2>
          <p>Thẩm định nguồn mở theo ADR 004 & Spec 8.6, 12.1. Đạt chuẩn WCAG AA và phím tắt.</p>
        </div>

        <div className="acp-metrics-bar">
          <div className="acp-metric-card">
            <strong>{items.length}</strong>
            <span>Chờ duyệt</span>
          </div>
          <div className="acp-metric-card">
            <strong>{reviewedCount}</strong>
            <span>Đã duyệt phiên này</span>
          </div>
          <div className="acp-metric-card">
            <strong>
              {reviewedCount > 0
                ? `${(elapsedSecs / reviewedCount).toFixed(1)}s`
                : "0s"}
            </strong>
            <span>Tốc độ trung bình / nguồn</span>
          </div>
        </div>
      </header>

      {/* Shortcuts Guide Bar */}
      <div className="acp-shortcuts-pill" role="note" aria-label="Hướng dẫn phím tắt">
        <span>⚡ <strong>Phím tắt:</strong></span>
        <span><kbd className="acp-key">J</kbd> / <kbd className="acp-key">↓</kbd> Nguồn tiếp theo</span>
        <span><kbd className="acp-key">K</kbd> / <kbd className="acp-key">↑</kbd> Nguồn trước</span>
        <span><kbd className="acp-key">V</kbd> Duyệt (Verify)</span>
        <span><kbd className="acp-key">R</kbd> Loại (Reject)</span>
      </div>

      {toast && (
        <div className="acp-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}

      {/* Filters Bar */}
      <div className="acp-filters-bar" role="search" aria-label="Bộ lọc nguồn">
        <div className="acp-filter-group">
          <label htmlFor="filter-provider">Provider:</label>
          <select
            id="filter-provider"
            className="acp-select"
            value={providerFilter}
            onChange={(e) => {
              setProviderFilter(e.target.value);
              setSelectedIndex(0);
            }}
          >
            <option value="all">Tất cả ({items.length})</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div className="acp-filter-group">
          <label htmlFor="filter-reason">Lý do duyệt:</label>
          <select
            id="filter-reason"
            className="acp-select"
            value={reasonFilter}
            onChange={(e) => {
              setReasonFilter(e.target.value);
              setSelectedIndex(0);
            }}
          >
            <option value="all">Tất cả lý do</option>
            <option value="license_unknown">Chưa rõ bản quyền (license_unknown)</option>
            <option value="unsure_labels">Nhãn chủ đề chưa chắc (unsure_labels)</option>
            <option value="robots">Quy định robots / domain</option>
          </select>
        </div>

        <div className="acp-filter-group" style={{ flex: 1 }}>
          <label htmlFor="filter-search">Tìm kiếm:</label>
          <input
            id="filter-search"
            type="search"
            className="acp-input"
            placeholder="Tìm theo tiêu đề, URL, provider…"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setSelectedIndex(0);
            }}
            style={{ width: "100%" }}
          />
        </div>
      </div>

      {loading && <p aria-busy="true">Đang tải danh sách chờ duyệt…</p>}
      {error && <p role="alert" className="row-error">{error}</p>}

      {/* Main Review Workspace */}
      {!loading && !error && filteredItems.length === 0 && (
        <div className="card" style={{ padding: "2rem", textAlign: "center" }}>
          <h3>🎉 Hàng chờ rỗng</h3>
          <p>Tất cả tài nguyên catalog đã được thẩm định xong!</p>
        </div>
      )}

      {!loading && filteredItems.length > 0 && selectedItem && (
        <div className="acp-workspace">
          {/* Left Column: Queue List */}
          <div
            className="acp-queue-column"
            role="list"
            aria-label="Danh sách tài nguyên chờ duyệt"
          >
            {filteredItems.map((item, idx) => {
              const reviewChecks = item.checks.filter(
                (c) => c.result === "review" || c.result === "fail"
              );
              return (
                <div
                  key={item.id}
                  role="listitem"
                  tabIndex={0}
                  className={`acp-queue-item ${idx === selectedIndex ? "active" : ""}`}
                  onClick={() => setSelectedIndex(idx)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      setSelectedIndex(idx);
                    }
                  }}
                  aria-selected={idx === selectedIndex}
                >
                  <h4 className="acp-qi-title">
                    {idx + 1}. {item.title}
                  </h4>
                  <div className="acp-qi-meta">
                    <span>🏫 {item.provider}</span>
                    {item.license ? (
                      <span>📜 {item.license}</span>
                    ) : (
                      <span style={{ color: "var(--color-warning)" }}>⚠️ Chưa có license</span>
                    )}
                    {reviewChecks.length > 0 ? (
                      <span className="acp-check-pill review">
                        {reviewChecks.length} cần xem
                      </span>
                    ) : (
                      <span className="acp-check-pill pass">Đủ điều kiện</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right Column: Detailed Inspector & Action Box */}
          <section
            className="acp-inspector-column"
            aria-label="Chi tiết kiểm tra & quyết định"
          >
            <div className="acp-inspector-header">
              <span className="acp-check-pill review" style={{ width: "fit-content" }}>
                Nguồn {selectedIndex + 1} / {filteredItems.length}
              </span>
              <h3 className="acp-inspector-title">{selectedItem.title}</h3>
              <div className="acp-inspector-url">
                🌐 URL:{" "}
                <a
                  href={selectedItem.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Mở liên kết gốc trong tab mới"
                >
                  {selectedItem.url} ↗
                </a>
              </div>
            </div>

            {/* Verification Checks Breakdown */}
            <div>
              <h4 className="acp-section-title">Kết quả kiểm tra tự động (4 checks)</h4>
              <div className="acp-checks-list">
                {selectedItem.checks.map((chk) => (
                  <div key={chk.check} className="acp-check-row">
                    <div>
                      <span className="acp-check-name">{chk.check}:</span>
                      <span className="acp-check-reason">{chk.reason}</span>
                    </div>
                    <span className={`acp-check-pill ${chk.result}`}>
                      {chk.result.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* License the admin confirms */}
            <div className="acp-edit-grid">
              <div className="acp-form-field">
                <label htmlFor="edit-license">Giấy phép (License):</label>
                <select
                  id="edit-license"
                  className="acp-select"
                  value={license}
                  onChange={(e) => setLicenseChoice((prev) => ({ ...prev, [selectedItem.id]: e.target.value }))}
                >
                  <option value="">— Giữ giấy phép đã nhận diện —</option>
                  {LICENSES.map((lic) => (
                    <option key={lic} value={lic}>
                      {lic}
                    </option>
                  ))}
                </select>
              </div>

            </div>

            {/* Decision Controls */}
            <div className="acp-decision-box">
              <h4 className="acp-section-title" style={{ margin: 0 }}>
                Quyết định duyệt / loại nguồn
              </h4>

              <div className="acp-form-field">
                <label htmlFor="verify-reason">Lý do duyệt:</label>
                <input
                  id="verify-reason"
                  type="text"
                  className="acp-input"
                  value={customReason}
                  onChange={(e) => setCustomReason(e.target.value)}
                />
                <div className="acp-preset-reasons">
                  {PRESET_VERIFY_REASONS.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className="acp-preset-btn"
                      onClick={() => setCustomReason(r)}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div className="acp-form-field">
                <label htmlFor="reject-reason">Lý do từ chối (nếu loại):</label>
                <input
                  id="reject-reason"
                  type="text"
                  className="acp-input"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
                <div className="acp-preset-reasons">
                  {PRESET_REJECT_REASONS.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className="acp-preset-btn"
                      onClick={() => setRejectReason(r)}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div className="acp-decision-buttons">
                <button
                  type="button"
                  className="acp-btn-verify"
                  onClick={() => void handleVerify()}
                  disabled={busy}
                  aria-label="Xác nhận duyệt nguồn này (phím tắt V)"
                >
                  ✓ [V] Duyệt nguồn (Verify)
                </button>
                <button
                  type="button"
                  className="acp-btn-reject"
                  onClick={() => void handleReject()}
                  disabled={busy}
                  aria-label="Từ chối loại bỏ nguồn này (phím tắt R)"
                >
                  ✕ [R] Loại nguồn (Reject)
                </button>
              </div>

              <div className="acp-nav-actions">
                <button
                  type="button"
                  className="acp-preset-btn"
                  onClick={() => setSelectedIndex((prev) => Math.max(0, prev - 1))}
                  disabled={selectedIndex === 0}
                >
                  ← [K] Nguồn trước
                </button>
                <span>
                  {selectedIndex + 1} / {filteredItems.length}
                </span>
                <button
                  type="button"
                  className="acp-preset-btn"
                  onClick={() =>
                    setSelectedIndex((prev) =>
                      Math.min(filteredItems.length - 1, prev + 1)
                    )
                  }
                  disabled={selectedIndex >= filteredItems.length - 1}
                >
                  [J] Nguồn sau →
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
