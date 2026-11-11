import React from "react";
import "./GraphListView.css";

export interface GraphListNode {
  id: string;
  title: string;
  type: "topic" | "milestone";
  week?: number | null;
  layer?: number | null;
  est_minutes?: number | null;
  status?: string;
  sources_status?: string;
  sources_count?: number;
  clo?: string[];
  prereqs_count?: number;
}

export interface GraphListViewProps {
  nodes: GraphListNode[];
  selectedId?: string | null;
  onSelect: (nodeId: string) => void;
  className?: string;
}

const STATUS_LABELS: Record<string, { text: string; className: string }> = {
  mastered: { text: "Đã vững", className: "status-mastered" },
  in_progress: { text: "Đang học", className: "status-in-progress" },
  review_due: { text: "Cần ôn tập", className: "status-review-due" },
  not_started: { text: "Chưa học", className: "status-not-started" },
};

export function GraphListView({
  nodes,
  selectedId,
  onSelect,
  className = "",
}: GraphListViewProps) {
  // Sort nodes primarily by week, then by type/title
  const sortedNodes = [...nodes].sort((a, b) => {
    const wA = a.week ?? a.layer ?? 1;
    const wB = b.week ?? b.layer ?? 1;
    if (wA !== wB) return wA - wB;
    return a.title.localeCompare(b.title, "vi");
  });

  return (
    <div
      className={`kg-list-view-container ${className}`}
      role="region"
      aria-label="Danh sách chặng học tiếp cận"
    >
      <table className="kg-accessible-table">
        <caption className="sr-only">
          Danh sách toàn bộ chặng học theo thứ tự tuần và trạng thái tiến độ
        </caption>
        <thead>
          <tr>
            <th scope="col" className="col-week">Tuần</th>
            <th scope="col" className="col-title">Chặng học</th>
            <th scope="col" className="col-type">Phân loại</th>
            <th scope="col" className="col-status">Trạng thái</th>
            <th scope="col" className="col-sources">Nguồn kiểm chứng</th>
            <th scope="col" className="col-clo">Chuẩn đầu ra</th>
            <th scope="col" className="col-action">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {sortedNodes.length === 0 ? (
            <tr>
              <td colSpan={7} className="empty-message">
                Không tìm thấy chặng học phù hợp với bộ lọc hiện tại.
              </td>
            </tr>
          ) : (
            sortedNodes.map((node) => {
              const isSelected = selectedId === node.id;
              const statusInfo =
                STATUS_LABELS[node.status || "not_started"] ||
                STATUS_LABELS.not_started;

              return (
                <tr
                  key={node.id}
                  className={`kg-list-row ${isSelected ? "selected" : ""}`}
                  aria-selected={isSelected}
                  onClick={() => onSelect(node.id)}
                >
                  <td className="cell-week">
                    {node.week ? `Tuần ${node.week}` : "—"}
                  </td>
                  <td className="cell-title">
                    <button
                      type="button"
                      className="node-title-button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(node.id);
                      }}
                      aria-label={`Chọn chặng ${node.title}`}
                    >
                      {node.title}
                    </button>
                    {node.est_minutes && (
                      <span className="duration-hint">
                        ({node.est_minutes} phút)
                      </span>
                    )}
                  </td>
                  <td className="cell-type">
                    <span
                      className={`type-badge ${
                        node.type === "milestone" ? "milestone" : "topic"
                      }`}
                    >
                      {node.type === "milestone" ? "💎 Mốc thi" : "📘 Chủ đề"}
                    </span>
                  </td>
                  <td className="cell-status">
                    <span className={`status-badge ${statusInfo.className}`}>
                      <span className="status-indicator" aria-hidden="true" />
                      {statusInfo.text}
                    </span>
                  </td>
                  <td className="cell-sources">
                    {node.sources_status === "insufficient" ? (
                      <span className="sources-badge insufficient" title="Cần bổ sung nguồn kiểm chứng">
                        ⚠️ Chưa đủ
                      </span>
                    ) : (
                      <span className="sources-badge sufficient">
                        ✓ {node.sources_count ?? 3} nguồn
                      </span>
                    )}
                  </td>
                  <td className="cell-clo">
                    {node.clo && node.clo.length > 0 ? (
                      <div className="clo-tags">
                        {node.clo.map((c) => (
                          <span key={c} className="clo-tag">
                            {c}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="cell-action">
                    <button
                      type="button"
                      className="btn-select-action"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(node.id);
                      }}
                    >
                      {isSelected ? "Đang chọn" : "Chi tiết"}
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
