import { useState, useRef, useEffect, type ReactNode } from "react";
import "./VerifiedSourceCard.css";

export type VerifiedSource = {
  id: string;
  source_id?: string | null;
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
  kind?: "user_material" | "catalog" | "web" | "external";
  pinned?: boolean;
};

export type VerifiedSourceCardProps = {
  source: VerifiedSource;
  compact?: boolean;
  onFeedback?: (helpful: boolean) => void;
  onPin?: (pinned: boolean) => void;
  actions?: ReactNode;
  className?: string;
};

const formatNames: Record<string, string> = {
  video: "Video",
  article: "Article / Reading",
  exercise: "Exercise",
  book: "Book / PDF",
  course: "Course",
  paper: "Research paper",
};

export function formatLabel(format?: string): string {
  if (!format) return "Material";
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
  onPin,
  actions,
  className = "",
}: VerifiedSourceCardProps) {
  const [showCriteria, setShowCriteria] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close tooltip on click outside or Escape
  useEffect(() => {
    if (!showCriteria) return;
    const handleClick = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
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
  const isExternal = source.kind === "external" || source.kind === "web";
  const isUserMaterial = source.kind === "user_material";
  // CRITICAL RULE: External or web sources NEVER carry the verified badge!
  const isVerified =
    !isExternal && !isUserMaterial && source.verification_status === "verified";
  const breakdownEntries = Object.entries(source.breakdown || {});
  const hasBreakdown = breakdownEntries.length > 0;

  return (
    <article
      className={`verified-source-card ${compact ? "compact" : ""} ${source.pinned ? "pinned" : ""} ${className}`}
      aria-label={`Learning source: ${source.title}`}
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
            <span className="vsc-domain-chip" title="Actual domain">
              🌐 <strong>{domain}</strong>
            </span>
          )}
        </div>

        <div className="vsc-badges">
          {isUserMaterial && (
            <span
              className="vsc-badge vsc-badge-user-material"
              title="Material uploaded by you"
            >
              📂 Your material
            </span>
          )}

          {isExternal && (
            <span
              className="vsc-badge vsc-badge-external"
              title="External source not yet verified"
              aria-label="External source (unverified)"
            >
              🌐 External source (unverified)
            </span>
          )}

          {isVerified && (
            <div className="vsc-criteria-popover" ref={popoverRef}>
              <button
                type="button"
                className="vsc-badge vsc-badge-verified"
                onClick={() => setShowCriteria(!showCriteria)}
                aria-expanded={showCriteria}
                aria-label="View verified source criteria"
                title="Click to view verification criteria"
              >
                ✓ Verified{" "}
                {source.verified_at ? `· ${source.verified_at}` : ""}
              </button>

              {showCriteria && (
                <div
                  className="vsc-criteria-tooltip"
                  role="tooltip"
                  aria-label="Source verification criteria"
                >
                  {/* The four checks of app/catalog/verification.py CHECKS (#101). */}
                  <h4>Trusted source verification criteria</h4>
                  <ul>
                    <li>
                      <strong>Fetchable:</strong> page loads cleanly, robots.txt
                      allows access, and readable content is present.
                    </li>
                    <li>
                      <strong>Domain:</strong> belongs to an institution or
                      educational provider on the trusted list.
                    </li>
                    <li>
                      <strong>License:</strong> clear, recognized open license.
                    </li>
                    <li>
                      <strong>Metadata:</strong> valid title, format, and
                      language metadata.
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

          {source.duration_min ? (
            <span className="vsc-badge vsc-badge-duration">
              ⏱ {source.duration_min} min
            </span>
          ) : null}

          {source.license && (
            <span
              className="vsc-badge vsc-badge-license"
              title="Content license"
            >
              📜 {source.license}
            </span>
          )}

          {source.score !== undefined && !hasBreakdown && (
            <span className="vsc-badge vsc-badge-score">
              ★ {Math.round(source.score * 100)}%
            </span>
          )}
        </div>
      </div>

      {institutionOrProvider && (
        <div className="vsc-meta-line">
          <span className="vsc-institution">🏫 {institutionOrProvider}</span>
          {source.pages && source.pages.length > 0 && (
            <span>· Page {source.pages.join(", ")}</span>
          )}
        </div>
      )}

      {source.reason && (
        <p className="vsc-reason">
          <strong>Why selected:</strong> {source.reason}
        </p>
      )}

      {source.score !== undefined && hasBreakdown && (
        <details className="vsc-breakdown">
          <summary className="vsc-badge vsc-badge-score">
            ★ {Math.round(source.score * 100)}% ({breakdownEntries.length}{" "}
            criteria)
          </summary>
          <dl className="vsc-breakdown-grid">
            {breakdownEntries.map(([criterion, value]) => (
              <div key={criterion}>
                <dt>{criterion}</dt>
                <dd>{Math.round(value * 100)}%</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      {source.evidence_quote && (
        <blockquote className="vsc-quote-box" title="Supporting quote">
          "{source.evidence_quote}"
        </blockquote>
      )}

      {(onFeedback || onPin) && (
        <div className="vsc-actions">
          {onFeedback && (
            <>
              <button
                type="button"
                className="vsc-feedback-btn"
                onClick={() => onFeedback(true)}
                title="Mark this source as helpful"
              >
                👍 Helpful
              </button>
              <button
                type="button"
                className="vsc-feedback-btn"
                onClick={() => onFeedback(false)}
                title="Mark this source as not relevant"
              >
                👎 Not relevant
              </button>
            </>
          )}
          {onPin && (
            <button
              type="button"
              className={`vsc-pin-btn ${source.pinned ? "pinned" : ""}`}
              onClick={() => onPin(!source.pinned)}
              title={source.pinned ? "Unpin" : "Pin to top"}
            >
              {source.pinned ? "📌 Pinned" : "📌 Pin"}
            </button>
          )}
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
        <h4 className="vsc-insufficient-title">No suitable sources found yet</h4>
      </div>
      <p className="vsc-insufficient-desc">
        Not enough open educational resources meeting the verification quality
        threshold (≥ 0.65) were found for this stage yet.
      </p>
      {onRetry && (
        <div>
          <button
            type="button"
            className="vsc-feedback-btn"
            onClick={onRetry}
            disabled={busy}
          >
            {busy ? "Searching…" : "Search again"}
          </button>
        </div>
      )}
    </div>
  );
}
