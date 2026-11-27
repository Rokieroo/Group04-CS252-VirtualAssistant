import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Page } from "../navigation";
import type { RoadmapNode } from "../api/types";
import { fetchDueReviews, type DueReviewCard } from "../api/reviews";
import { writeGraphState, defaultGraphFilters } from "../api/graphState";
import { today } from "../time";
import "./TodayPage.css";

export type TodayPageProps = {
  go: (page: Page) => void;
  onOpenNodeOnGraph?: (nodeId: string, roadmapId?: string) => void;
  roadmapId?: string;
  nodes?: RoadmapNode[];
};

export function TodayPage({
  go,
  onOpenNodeOnGraph,
  roadmapId = "",
  nodes = [],
}: TodayPageProps) {
  const [reviews, setReviews] = useState<DueReviewCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);

  const loadReviews = useCallback(async () => {
    const version = ++requestVersion.current;
    try {
      setLoading(true);
      setError("");
      const dueCards = await fetchDueReviews(20);
      if (version !== requestVersion.current) return;
      setReviews(dueCards);
    } catch {
      if (version !== requestVersion.current) return;
      // Graceful fallback for mock or demo mode
      setReviews([]);
    } finally {
      if (version === requestVersion.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadReviews();
    return () => {
      ++requestVersion.current;
    };
  }, [loadReviews]);

  const openNode = (nodeId: string) => {
    writeGraphState(defaultGraphFilters, nodeId, "week");
    if (onOpenNodeOnGraph) {
      onOpenNodeOnGraph(nodeId, roadmapId);
    } else {
      if (roadmapId) {
        window.location.hash = `roadmaps/${encodeURIComponent(roadmapId)}/graph/${encodeURIComponent(nodeId)}`;
      }
      go("Roadmap");
    }
  };

  // Partition due topics and upcoming milestones in one pass when nodes change
  const { dueTopics, milestones } = useMemo(() => {
    const topics: RoadmapNode[] = [];
    const checks: RoadmapNode[] = [];
    for (const node of nodes) {
      if (node.type === "topic" || node.kind === "topic") topics.push(node);
      else if (node.type === "milestone" || node.kind === "milestone")
        checks.push(node);
    }
    return { dueTopics: topics, milestones: checks };
  }, [nodes]);

  const formattedDate = today().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="today-page" aria-label="Today view">
      <header className="today-header">
        <div className="today-header-content">
          <h2 className="today-title">Today</h2>
          <p className="today-date">📅 {formattedDate}</p>
        </div>
      </header>

      {/* Quick Summary Metrics */}
      <section className="today-metrics-grid" aria-label="Today overview">
        <div className="today-metric-card">
          <span className="today-metric-icon">📍</span>
          <div className="today-metric-text">
            <strong>{dueTopics.length}</strong>
            <span>Stages to study</span>
          </div>
        </div>

        <div className="today-metric-card">
          <span className="today-metric-icon">🔄</span>
          <div className="today-metric-text">
            <strong>{reviews.length}</strong>
            <span>FSRS reviews</span>
          </div>
        </div>

        <div className="today-metric-card">
          <span className="today-metric-icon">💎</span>
          <div className="today-metric-text">
            <strong>{milestones.length}</strong>
            <span>Milestones</span>
          </div>
        </div>
      </section>

      {loading && (
        <div className="today-loading" role="status">
          <span>⏳ Loading today's study plan…</span>
        </div>
      )}

      {error && (
        <div className="row-error" role="alert">
          <p>{error}</p>
          <button type="button" className="button" onClick={() => void loadReviews()}>
            Retry
          </button>
        </div>
      )}

      {/* Section 1: Due Learning Steps */}
      <section className="today-section" aria-label="Stages due today">
        <div className="today-section-header">
          <h3 className="today-section-title">📍 Stages due today</h3>
          <span className="today-section-badge">{dueTopics.length} stages</span>
        </div>

        {dueTopics.length === 0 ? (
          <div className="today-empty-card" role="status">
            <span aria-hidden="true">🎉</span>
            <p>Great work! You have no overdue learning stages today.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {dueTopics.map((node) => (
              <article key={node.id} className="today-card-item">
                <div className="today-card-main">
                  <h4 className="today-card-title">{node.title}</h4>
                  <div className="today-card-meta">
                    {node.week && (
                      <span className="today-chip">Week {node.week}</span>
                    )}
                    {(node.est_minutes || node.duration_minutes) && (
                      <span className="today-chip">
                        ⏱ {node.est_minutes || node.duration_minutes} min
                      </span>
                    )}
                    <span className="today-chip today-chip-status">Due</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => openNode(node.id)}
                  aria-label={`Open stage ${node.title} on Knowledge Graph`}
                >
                  Open on Graph →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Section 2: Spaced Repetition Reviews */}
      <section className="today-section" aria-label="Due FSRS reviews">
        <div className="today-section-header">
          <h3 className="today-section-title">🔄 FSRS reviews</h3>
          <span className="today-section-badge">{reviews.length} reviews</span>
        </div>

        {reviews.length === 0 ? (
          <div className="today-empty-card" role="status">
            <span aria-hidden="true">✓</span>
            <p>You have completed all FSRS review cards due today.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {reviews.map((rev) => (
              <article key={rev.item_id} className="today-card-item">
                <div className="today-card-main">
                  <h4 className="today-card-title">{rev.prompt}</h4>
                  <div className="today-card-meta">
                    <span className="today-chip">
                      {rev.type === "mcq" ? "Multiple choice" : "Short answer"}
                    </span>
                    <span className="today-chip today-chip-review">Review due</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => {
                    if (rev.node_id) openNode(rev.node_id);
                    else go("Roadmap");
                  }}
                  aria-label={`Open review ${rev.prompt} on Knowledge Graph`}
                >
                  Review stage →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Section 3: Upcoming Milestones & Exams */}
      <section className="today-section" aria-label="Upcoming milestones">
        <div className="today-section-header">
          <h3 className="today-section-title">💎 Upcoming milestones</h3>
          <span className="today-section-badge">{milestones.length} milestones</span>
        </div>

        {milestones.length === 0 ? (
          <div className="today-empty-card" role="status">
            <p>No upcoming exams or milestones.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {milestones.map((node) => (
              <article key={node.id} className="today-card-item today-card-milestone">
                <div className="today-card-main">
                  <h4 className="today-card-title">💎 {node.title}</h4>
                  <div className="today-card-meta">
                    {node.week && (
                      <span className="today-chip">Week {node.week}</span>
                    )}
                    {node.covers && node.covers.length > 0 && (
                      <span className="today-chip">
                        Covers {node.covers.length} stages
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => openNode(node.id)}
                  aria-label={`View milestone ${node.title} on Knowledge Graph`}
                >
                  View on Graph →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
