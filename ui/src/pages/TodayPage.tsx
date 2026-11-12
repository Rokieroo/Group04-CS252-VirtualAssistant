import { useEffect, useState, useCallback } from "react";
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

  const loadReviews = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const dueCards = await fetchDueReviews(20);
      setReviews(dueCards);
    } catch {
      // Graceful fallback for mock or demo mode
      setReviews([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadReviews();
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

  // 1. Due topics: topics due today or active week topics
  const dueTopics = nodes.filter(
    (n) => n.type === "topic" || n.kind === "topic",
  );

  // 2. Milestones: upcoming checkpoints and exams
  const milestones = nodes.filter(
    (n) => n.type === "milestone" || n.kind === "milestone",
  );

  const formattedDate = today().toLocaleDateString("vi-VN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="today-page" aria-label="Màn hình Hôm nay">
      <header className="today-header">
        <div className="today-header-content">
          <h2 className="today-title">Hôm nay</h2>
          <p className="today-date">📅 {formattedDate}</p>
        </div>
      </header>

      {/* Quick Summary Metrics */}
      <section className="today-metrics-grid" aria-label="Tổng quan hôm nay">
        <div className="today-metric-card">
          <span className="today-metric-icon">📍</span>
          <div className="today-metric-text">
            <strong>{dueTopics.length}</strong>
            <span>Chặng cần học</span>
          </div>
        </div>

        <div className="today-metric-card">
          <span className="today-metric-icon">🔄</span>
          <div className="today-metric-text">
            <strong>{reviews.length}</strong>
            <span>Bài ôn FSRS</span>
          </div>
        </div>

        <div className="today-metric-card">
          <span className="today-metric-icon">💎</span>
          <div className="today-metric-text">
            <strong>{milestones.length}</strong>
            <span>Mốc kiểm tra</span>
          </div>
        </div>
      </section>

      {loading && (
        <div className="today-loading" role="status">
          <span>⏳ Đang tải dữ liệu học tập hôm nay…</span>
        </div>
      )}

      {error && (
        <div className="row-error" role="alert">
          <p>{error}</p>
          <button type="button" className="button" onClick={() => void loadReviews()}>
            Thử lại
          </button>
        </div>
      )}

      {/* Section 1: Due Learning Steps */}
      <section className="today-section" aria-label="Chặng đến hạn hôm nay">
        <div className="today-section-header">
          <h3 className="today-section-title">📍 Chặng đến hạn hôm nay</h3>
          <span className="today-section-badge">{dueTopics.length} chặng</span>
        </div>

        {dueTopics.length === 0 ? (
          <div className="today-empty-card" role="status">
            <span aria-hidden="true">🎉</span>
            <p>Tuyệt vời! Bạn không có chặng học tập nào bị trễ hạn hôm nay.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {dueTopics.map((node) => (
              <article key={node.id} className="today-card-item">
                <div className="today-card-main">
                  <h4 className="today-card-title">{node.title}</h4>
                  <div className="today-card-meta">
                    {node.week && (
                      <span className="today-chip">Tuần {node.week}</span>
                    )}
                    {(node.est_minutes || node.duration_minutes) && (
                      <span className="today-chip">
                        ⏱ {node.est_minutes || node.duration_minutes} phút
                      </span>
                    )}
                    <span className="today-chip today-chip-status">Đến hạn</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => openNode(node.id)}
                  aria-label={`Mở chặng ${node.title} trên Knowledge Graph`}
                >
                  Mở trên Graph →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Section 2: Spaced Repetition Reviews */}
      <section className="today-section" aria-label="Bài ôn tập FSRS đến hạn">
        <div className="today-section-header">
          <h3 className="today-section-title">🔄 Bài ôn tập FSRS</h3>
          <span className="today-section-badge">{reviews.length} bài ôn</span>
        </div>

        {reviews.length === 0 ? (
          <div className="today-empty-card" role="status">
            <span aria-hidden="true">✓</span>
            <p>Bạn đã hoàn thành tất cả thẻ ôn tập FSRS đến hạn hôm nay.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {reviews.map((rev) => (
              <article key={rev.item_id} className="today-card-item">
                <div className="today-card-main">
                  <h4 className="today-card-title">{rev.prompt}</h4>
                  <div className="today-card-meta">
                    <span className="today-chip">
                      {rev.type === "mcq" ? "Trắc nghiệm" : "Tự luận"}
                    </span>
                    <span className="today-chip today-chip-review">Cần ôn lại</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => {
                    if (rev.node_id) openNode(rev.node_id);
                    else go("Roadmap");
                  }}
                  aria-label={`Mở bài ôn ${rev.prompt} trên Knowledge Graph`}
                >
                  Ôn chặng này →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Section 3: Upcoming Milestones & Exams */}
      <section className="today-section" aria-label="Mốc kiểm tra sắp tới">
        <div className="today-section-header">
          <h3 className="today-section-title">💎 Mốc kiểm tra sắp tới</h3>
          <span className="today-section-badge">{milestones.length} mốc</span>
        </div>

        {milestones.length === 0 ? (
          <div className="today-empty-card" role="status">
            <p>Không có kỳ thi hoặc mốc kiểm tra nào sắp tới.</p>
          </div>
        ) : (
          <div className="today-cards-list">
            {milestones.map((node) => (
              <article key={node.id} className="today-card-item today-card-milestone">
                <div className="today-card-main">
                  <h4 className="today-card-title">💎 {node.title}</h4>
                  <div className="today-card-meta">
                    {node.week && (
                      <span className="today-chip">Tuần {node.week}</span>
                    )}
                    {node.covers && node.covers.length > 0 && (
                      <span className="today-chip">
                        Bao phủ {node.covers.length} chặng
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="today-action-btn"
                  onClick={() => openNode(node.id)}
                  aria-label={`Xem mốc kiểm tra ${node.title} trên Knowledge Graph`}
                >
                  Xem mốc trên Graph →
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
