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
  known?: string | null;
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
  locked: { text: "Locked", className: "status-not-started" },
  available: { text: "Available", className: "status-in-progress" },
  unknown: { text: "No status", className: "status-not-started" },
  mastered: { text: "Mastered", className: "status-mastered" },
  known: { text: "Known", className: "status-mastered" },
  in_progress: { text: "In progress", className: "status-in-progress" },
  review_due: { text: "Review due", className: "status-review-due" },
  not_started: { text: "Not started", className: "status-not-started" },
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
      aria-label="Accessible stage list"
    >
      <table className="kg-accessible-table">
        <caption className="sr-only">
          Complete list of learning stages ordered by week and progress status
        </caption>
        <thead>
          <tr>
            <th scope="col" className="col-week">
              Week
            </th>
            <th scope="col" className="col-title">
              Stage
            </th>
            <th scope="col" className="col-type">
              Type
            </th>
            <th scope="col" className="col-status">
              Status
            </th>
            <th scope="col" className="col-sources">
              Verified sources
            </th>
            <th scope="col" className="col-clo">
              Learning outcomes
            </th>
            <th scope="col" className="col-action">
              Action
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedNodes.length === 0 ? (
            <tr>
              <td colSpan={7} className="empty-message">
                No stages match the current filters.
              </td>
            </tr>
          ) : (
            sortedNodes.map((node) => {
              const isSelected = selectedId === node.id;
              const statusInfo =
                STATUS_LABELS[node.known ? "known" : node.status || "unknown"] ||
                STATUS_LABELS.unknown;

              return (
                <tr
                  key={node.id}
                  className={`kg-list-row ${isSelected ? "selected" : ""}`}
                  aria-selected={isSelected}
                  onClick={() => onSelect(node.id)}
                >
                  <td className="cell-week">
                    {node.week ? `Week ${node.week}` : "—"}
                  </td>
                  <td className="cell-title">
                    <button
                      type="button"
                      className="node-title-button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(node.id);
                      }}
                      aria-label={`Select stage ${node.title}`}
                    >
                      {node.title}
                    </button>
                    {node.est_minutes && (
                      <span className="duration-hint">
                        ({node.est_minutes} min)
                      </span>
                    )}
                  </td>
                  <td className="cell-type">
                    <span
                      className={`type-badge ${
                        node.type === "milestone" ? "milestone" : "topic"
                      }`}
                    >
                      {node.type === "milestone" ? "💎 Milestone" : "📘 Topic"}
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
                      <span className="sources-badge">Checking</span>
                    ) : node.sources_status === "insufficient" ||
                      node.verified_sources_count === 0 ? (
                      <span
                        className="sources-badge insufficient"
                        title="Needs more verified sources"
                      >
                        ⚠️ Insufficient
                        {node.verified_sources_count !== undefined
                          ? ` · ${node.verified_sources_count} verified sources`
                          : ""}
                      </span>
                    ) : (
                      <span className="sources-badge sufficient">
                        {node.sources_status === "pending"
                          ? "Checking"
                          : `✓ ${node.verified_sources_count ?? node.sources_count ?? 0} sources`}
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
                      {isSelected ? "Selected" : "Details"}
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
