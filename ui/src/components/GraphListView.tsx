import { topologicalNodes } from "../api/graphState";
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
  verified_sources_count?: number;
  clo?: string[];
  prereqs_count?: number;
}

export interface GraphListViewProps {
  nodes: GraphListNode[];
  orderingNodes?: GraphListNode[];
  edges?: { parent_id: string; child_id: string }[];
  selectedId?: string | null;
  onSelect: (nodeId: string) => void;
  className?: string;
}

const STATUS_LABELS: Record<string, { text: string; className: string }> = {
  locked: { text: "Đang khóa", className: "status-not-started" },
  available: { text: "Có thể học", className: "status-in-progress" },
  unknown: { text: "Chưa có trạng thái", className: "status-not-started" },
  mastered: { text: "Đã vững", className: "status-mastered" },
  in_progress: { text: "Đang học", className: "status-in-progress" },
  review_due: { text: "Cần ôn tập", className: "status-review-due" },
  not_started: { text: "Chưa học", className: "status-not-started" },
};

export function GraphListView({
  nodes,
  orderingNodes,
  edges = [],
  selectedId,
  onSelect,
  className = "",
}: GraphListViewProps) {
  // Preserve prerequisite order even when intermediate nodes are filtered out.
  const visible = new Set(nodes.map((n) => n.id));
  const sortedNodes = topologicalNodes(orderingNodes || nodes, edges).filter(
    (n) => visible.has(n.id),
  );

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
            <th scope="col" className="col-week">
              Tuần
            </th>
            <th scope="col" className="col-title">
              Chặng học
            </th>
            <th scope="col" className="col-type">
              Phân loại
            </th>
            <th scope="col" className="col-status">
              Trạng thái
            </th>
            <th scope="col" className="col-sources">
              Nguồn kiểm chứng
            </th>
            <th scope="col" className="col-clo">
              Chuẩn đầu ra
            </th>
            <th scope="col" className="col-action">
              Thao tác
            </th>
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
                STATUS_LABELS[node.status || "unknown"] ||
                STATUS_LABELS.unknown;

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
                    {node.sources_status === "pending" ||
                    !node.sources_status ? (
                      <span className="sources-badge">Đang kiểm tra</span>
                    ) : node.sources_status === "insufficient" ||
                      node.verified_sources_count === 0 ? (
                      <span
                        className="sources-badge insufficient"
                        title="Cần bổ sung nguồn kiểm chứng"
                      >
                        ⚠️ Chưa đủ
                        {node.verified_sources_count !== undefined
                          ? ` · ${node.verified_sources_count} nguồn đã xác minh`
                          : ""}
                      </span>
                    ) : (
                      <span className="sources-badge sufficient">
                        {node.sources_status === "pending"
                          ? "Đang kiểm tra"
                          : `✓ ${node.verified_sources_count ?? node.sources_count ?? 0} nguồn`}
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
