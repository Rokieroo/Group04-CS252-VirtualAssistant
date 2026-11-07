import { useState, useRef, useEffect, type ReactNode } from "react";
import "./VerifiedSourceCard.css";

export type VerifiedSource = {
  id: string;
  title: string;
  url?: string | null;
  domain?: string;
  institution?: string;
  provider?: string;
  license?: string | null;
  format?: string;
  duration_min?: number | null;
  verification_status?: string;
  verified_at?: string;
  score?: number;
  breakdown?: Record<string, number>;
  reason?: string;
  evidence_quote?: string;
  pages?: number[];
  kind?: "user_material" | "catalog" | "web";
};

export type VerifiedSourceCardProps = {
  source: VerifiedSource;
  compact?: boolean;
  onFeedback?: (helpful: boolean) => void;
  actions?: ReactNode;
  className?: string;
};

const formatNames: Record<string, string> = {
  video: "Video",
  article: "Bài viết / Đọc",
  exercise: "Bài tập",
  book: "Sách / PDF",
  course: "Khóa học",
  paper: "Bài báo khoa học",
};

export function formatLabel(format?: string): string {
  if (!format) return "Tài liệu";
  return formatNames[format.toLowerCase()] || format;
}

/**
 * Shared Verified Source Card (Issue #104, Spec 8.6, 8.7, 12.1).
 * Reusable between S6 Stage page (#58) and Knowledge Graph node panel (#94, #109).
 */
export function VerifiedSourceCard({
  source,
  compact = false,
  onFeedback,
  actions,
  className = "",
}: VerifiedSourceCardProps) {
  const [showCriteria, setShowCriteria] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close tooltip on click outside or Escape
  useEffect(() => {
    if (!showCriteria) return;
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowCriteria(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowCriteria(false);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showCriteria]);

  const domain =
    source.domain ||
    (source.url
      ? (() => {
          try {
            return new URL(source.url).hostname;
          } catch {
            return "";
          }
        })()
      : "");

  const institutionOrProvider = source.institution || source.provider;
  const isVerified = source.verification_status === "verified" || !source.verification_status;

  return (
    <article
      className={`verified-source-card ${compact ? "compact" : ""} ${className}`}
      aria-label={`Nguồn học: ${source.title}`}
    >
      <div className="vsc-header">
        <div className="vsc-title-area">
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="vsc-title-link"
            >
              {source.title} ↗
            </a>
          ) : (
            <span className="vsc-title-link">{source.title}</span>
          )}

          {domain && (
            <span className="vsc-domain-chip" title="Tên miền thật">
              🌐 <strong>{domain}</strong>
            </span>
          )}
        </div>

        <div className="vsc-badges">
          {isVerified && (
            <div className="vsc-criteria-popover" ref={popoverRef}>
              <button
                type="button"
                className="vsc-badge vsc-badge-verified"
                onClick={() => setShowCriteria(!showCriteria)}
                aria-expanded={showCriteria}
                aria-label="Xem tiêu chí thẩm định nguồn đã xác minh"
                title="Nhấn để xem tiêu chí thẩm định"
              >
                ✓ Đã xác minh {source.verified_at ? `· ${source.verified_at}` : ""}
              </button>

              {showCriteria && (
                <div
                  className="vsc-criteria-tooltip"
                  role="tooltip"
                  aria-label="Tiêu chí thẩm định nguồn"
                >
                  <h4>Tiêu chí thẩm định nguồn uy tín</h4>
                  <ul>
                    <li>
                      <strong>Tên trường / uy tín:</strong> Nguồn từ các trường đại học hàng đầu hoặc tổ chức giáo dục chính thống.
                    </li>
                    <li>
                      <strong>Giấy phép mở:</strong> Nội dung có bản quyền OER/Creative Commons rõ ràng.
                    </li>
                    <li>
                      <strong>Độ tươi mới & sư phạm:</strong> Khớp mục tiêu bài học, giải thích sư phạm chuẩn xác.
                    </li>
                    <li>
                      <strong>Tuân thủ robots:</strong> Đảm bảo tôn trọng chính sách thu thập và quyền tác giả.
                    </li>
                  </ul>
                </div>
              )}
            </div>
          )}

          {source.format && (
            <span className="vsc-badge vsc-badge-format">
              {formatLabel(source.format)}
            </span>
          )}

          {source.duration_min && (
            <span className="vsc-badge vsc-badge-duration">
              ⏱ {source.duration_min} phút
            </span>
          )}

          {source.license && (
            <span className="vsc-badge vsc-badge-license" title="Giấy phép nội dung">
              📜 {source.license}
            </span>
          )}

          {source.score !== undefined && (
            <span
              className="vsc-badge vsc-badge-score"
              title={`Điểm chất lượng: ${(source.score * 100).toFixed(0)}%`}
            >
              ★ {(source.score * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {institutionOrProvider && (
        <div className="vsc-meta-line">
          <span className="vsc-institution">🏫 {institutionOrProvider}</span>
          {source.pages && source.pages.length > 0 && (
            <span>· Trang {source.pages.join(", ")}</span>
          )}
        </div>
      )}

      {source.reason && (
        <p className="vsc-reason">
          <strong>Lý do chọn:</strong> {source.reason}
        </p>
      )}

      {source.evidence_quote && (
        <blockquote className="vsc-quote-box" title="Đoạn trích minh chứng">
          "{source.evidence_quote}"
        </blockquote>
      )}

      {onFeedback && (
        <div className="vsc-actions">
          <button
            type="button"
            className="vsc-feedback-btn"
            onClick={() => onFeedback(true)}
            aria-label="Đánh giá nguồn này hữu ích"
          >
            👍 Hữu ích
          </button>
          <button
            type="button"
            className="vsc-feedback-btn"
            onClick={() => onFeedback(false)}
            aria-label="Đánh giá nguồn này không phù hợp"
          >
            👎 Không phù hợp
          </button>
        </div>
      )}

      {actions && <div className="vsc-custom-actions">{actions}</div>}
    </article>
  );
}

/**
 * Notice displayed when insufficient verified sources are found (Spec 8.6, Issue #58, #104).
 */
export function InsufficientSourcesNotice({
  onRetry,
  busy = false,
}: {
  onRetry?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="vsc-insufficient-notice" role="status">
      <div className="vsc-insufficient-header">
        <span aria-hidden="true">⚠️</span>
        <h4 className="vsc-insufficient-title">Chưa tìm được nguồn đủ tốt</h4>
      </div>
      <p className="vsc-insufficient-desc">
        Hệ thống chưa tìm thấy tài liệu mở đạt ngưỡng chất lượng thẩm định ≥ 0.65 cho chặng này.
      </p>
      {onRetry && (
        <div>
          <button
            type="button"
            className="vsc-feedback-btn"
            onClick={onRetry}
            disabled={busy}
          >
            {busy ? "Đang tìm kiếm…" : "Tìm lại"}
          </button>
        </div>
      )}
    </div>
  );
}
