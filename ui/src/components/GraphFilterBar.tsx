import React, { useEffect, useRef, useState } from "react";
import "./GraphFilterBar.css";

export interface FilterState {
  search: string;
  weekMin: number;
  weekMax: number;
  status:
    | "all"
    | "mastered"
    | "in_progress"
    | "review_due"
    | "not_started"
    | "locked"
    | "available";
  clo: string;
  verifiedOnly: boolean;
  hideSoftEdges: boolean;
  transitiveReduction: boolean;
  selectedMilestone: string;
  isLocalGraph: boolean;
  localDepth: number;
  viewMode: "graph" | "list";
}

export interface GraphFilterBarProps {
  nodes: Array<{
    id: string;
    title: string;
    type: "topic" | "milestone";
    week?: number | null;
    status?: string;
    clo?: string[];
    sources_status?: string;
  }>;
  filters: FilterState;
  onChange: (updated: FilterState) => void;
  onSelectNode: (nodeId: string) => void;
  className?: string;
}

export function GraphFilterBar({
  nodes,
  filters,
  onChange,
  onSelectNode,
  className = "",
}: GraphFilterBarProps) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [activeSuggestion, setActiveSuggestion] = useState(0);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  // Global keydown listener for '/' shortcut to focus search
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      const isInput =
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement ||
        activeEl instanceof HTMLSelectElement;

      if (
        e.key === "/" &&
        !isInput &&
        !(
          activeEl instanceof HTMLElement &&
          (activeEl.isContentEditable ||
            activeEl.closest("[role=dialog],dialog"))
        )
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
        setSuggestionsOpen(true);
      } else if (e.key === "Escape") {
        setSuggestionsOpen(false);
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  // Collect unique CLOs and Milestones
  const availableClos = Array.from(
    new Set(nodes.flatMap((n) => n.clo || []).filter(Boolean)),
  ).sort();

  const milestones = nodes.filter((n) => n.type === "milestone");

  // Autocomplete matching suggestions
  const suggestions =
    filters.search.trim().length > 0
      ? nodes
          .filter((n) =>
            n.title.toLowerCase().includes(filters.search.toLowerCase()),
          )
          .slice(0, 6)
      : [];

  const handleUpdate = (part: Partial<FilterState>) => {
    onChange({ ...filters, ...part });
  };

  return (
    <div
      className={`kg-filter-bar ${className}`}
      role="search"
      aria-label="Bộ lọc Knowledge Graph"
    >
      <div className="filter-row-primary">
        {/* Search input with '/' shortcut badge */}
        <div className="search-box-wrapper">
          <label htmlFor="kg-topic-search" className="sr-only">
            Tìm chặng học (nhấn phím /)
          </label>
          <div className="search-input-container">
            <span className="search-icon" aria-hidden="true">
              🔍
            </span>
            <input
              id="kg-topic-search"
              ref={searchInputRef}
              type="search"
              role="combobox"
              aria-controls="kg-suggestions"
              aria-activedescendant={
                suggestionsOpen && suggestions[activeSuggestion]
                  ? `kg-suggestion-${activeSuggestion}`
                  : undefined
              }
              onKeyDown={(e) => {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  setSuggestionsOpen(true);
                  setActiveSuggestion(
                    (i) =>
                      (i +
                        (e.key === "ArrowDown" ? 1 : -1) +
                        Math.max(1, suggestions.length)) %
                      Math.max(1, suggestions.length),
                  );
                } else if (
                  e.key === "Enter" &&
                  suggestionsOpen &&
                  suggestions.length
                ) {
                  e.preventDefault();
                  const item = suggestions[activeSuggestion] || suggestions[0];
                  handleUpdate({ search: item.title });
                  onSelectNode(item.id);
                  setSuggestionsOpen(false);
                } else if (e.key === "Escape") setSuggestionsOpen(false);
              }}
              className="kg-search-input"
              placeholder="Tìm chủ đề chặng học..."
              value={filters.search}
              onChange={(e) => {
                setActiveSuggestion(0);
                handleUpdate({ search: e.target.value });
                setSuggestionsOpen(true);
              }}
              onFocus={() => setSuggestionsOpen(true)}
              aria-expanded={suggestionsOpen && suggestions.length > 0}
              aria-autocomplete="list"
            />
            <kbd
              className="search-shortcut"
              title="Phím tắt: /"
              aria-hidden="true"
            >
              /
            </kbd>
          </div>

          {/* Autocomplete suggestions dropdown */}
          {suggestionsOpen && suggestions.length > 0 && (
            <ul
              id="kg-suggestions"
              className="search-suggestions-dropdown"
              role="listbox"
              aria-label="Matching topics"
            >
              {suggestions.map((item, index) => (
                <li
                  key={item.id}
                  role="option"
                  id={`kg-suggestion-${index}`}
                  aria-selected={activeSuggestion === index}
                  className="suggestion-item"
                  onMouseDown={() => {
                    handleUpdate({ search: item.title });
                    onSelectNode(item.id);
                    setSuggestionsOpen(false);
                  }}
                >
                  <span className="suggestion-type">
                    {item.type === "milestone" ? "💎 Mốc" : "📘 Chủ đề"}
                  </span>
                  <span className="suggestion-title">{item.title}</span>
                  {item.week && (
                    <span className="suggestion-week">Tuần {item.week}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Milestone selector: Tới mốc kiểm tra (Exam prep) */}
        <div className="filter-item milestone-filter">
          <label htmlFor="kg-milestone-select">Tới mốc kiểm tra:</label>
          <select
            id="kg-milestone-select"
            value={filters.selectedMilestone}
            onChange={(e) =>
              handleUpdate({ selectedMilestone: e.target.value })
            }
          >
            <option value="">Toàn bộ môn học</option>
            {milestones.map((m) => (
              <option value={m.id} key={m.id}>
                {m.title} {m.week ? `(Tuần ${m.week})` : ""}
              </option>
            ))}
          </select>
        </div>

        {/* View mode toggle (Graph vs List) */}
        <div className="view-mode-toggle" role="group" aria-label="Chế độ xem">
          <button
            type="button"
            className={filters.viewMode === "graph" ? "active" : ""}
            onClick={() => handleUpdate({ viewMode: "graph" })}
            title="Xem dạng Canvas đồ thị"
            aria-pressed={filters.viewMode === "graph"}
          >
            📊 Đồ thị
          </button>
          <button
            type="button"
            className={filters.viewMode === "list" ? "active" : ""}
            onClick={() => handleUpdate({ viewMode: "list" })}
            title="Xem dạng bảng danh sách tiếp cận (WCAG)"
            aria-pressed={filters.viewMode === "list"}
          >
            📋 Danh sách
          </button>
        </div>
      </div>

      <div className="filter-row-secondary">
        {/* Status filter */}
        <div className="filter-item">
          <label htmlFor="kg-status-filter">Trạng thái:</label>
          <select
            id="kg-status-filter"
            value={filters.status}
            onChange={(e) =>
              handleUpdate({
                status: e.target.value as FilterState["status"],
              })
            }
          >
            <option value="all">Tất cả</option>
            <option value="mastered">Đã vững</option>
            <option value="in_progress">Đang học</option>
            <option value="review_due">Cần ôn</option>
            <option value="locked">Đang khóa</option>
            <option value="available">Có thể học</option>
            <option value="not_started">Chưa học</option>
          </select>
        </div>

        {/* CLO filter */}
        {availableClos.length > 0 && (
          <div className="filter-item">
            <label htmlFor="kg-clo-filter">CLO:</label>
            <select
              id="kg-clo-filter"
              value={filters.clo}
              onChange={(e) => handleUpdate({ clo: e.target.value })}
            >
              <option value="">Mọi CLO</option>
              {availableClos.map((c) => (
                <option value={c} key={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Week range */}
        <div className="filter-item week-range-filter">
          <label htmlFor="kg-week-min">Tuần:</label>
          <input
            id="kg-week-min"
            type="number"
            min={1}
            max={filters.weekMax}
            value={filters.weekMin}
            onChange={(e) =>
              handleUpdate({
                weekMin: Math.min(
                  filters.weekMax,
                  Math.max(
                    1,
                    Math.min(52, Math.trunc(Number(e.target.value) || 1)),
                  ),
                ),
              })
            }
            aria-label="Tuần bắt đầu"
          />
          <span>–</span>
          <input
            id="kg-week-max"
            type="number"
            min={filters.weekMin}
            max={52}
            value={filters.weekMax}
            onChange={(e) =>
              handleUpdate({
                weekMax: Math.min(
                  52,
                  Math.max(
                    filters.weekMin,
                    Math.trunc(Number(e.target.value) || 1),
                  ),
                ),
              })
            }
            aria-label="Tuần kết thúc"
          />
        </div>

        {/* Checkbox: Chỉ chặng có nguồn đã kiểm chứng */}
        <label className="checkbox-item">
          <input
            type="checkbox"
            checked={filters.verifiedOnly}
            onChange={(e) => handleUpdate({ verifiedOnly: e.target.checked })}
          />
          <span>Nguồn đã kiểm chứng</span>
        </label>

        {/* Checkbox: Ẩn cạnh soft */}
        <label className="checkbox-item">
          <input
            type="checkbox"
            checked={filters.hideSoftEdges}
            onChange={(e) => handleUpdate({ hideSoftEdges: e.target.checked })}
          />
          <span>Ẩn cạnh tuần (soft)</span>
        </label>

        {/* Checkbox: Transitive reduction */}
        <label
          className="checkbox-item"
          title="Ẩn các cạnh bắc cầu suy ra được (a→b→c thì ẩn a→c)"
        >
          <input
            type="checkbox"
            checked={filters.transitiveReduction}
            onChange={(e) =>
              handleUpdate({ transitiveReduction: e.target.checked })
            }
          />
          <span>Thu gọn bắc cầu</span>
        </label>

        {/* Local graph controls */}
        <div className="local-graph-controls">
          <label className="checkbox-item">
            <input
              type="checkbox"
              checked={filters.isLocalGraph}
              onChange={(e) => handleUpdate({ isLocalGraph: e.target.checked })}
            />
            <span>Local graph</span>
          </label>
          {filters.isLocalGraph && (
            <div className="depth-slider-container">
              <label htmlFor="kg-depth-slider">
                Độ sâu: <strong>{filters.localDepth}</strong>
              </label>
              <input
                id="kg-depth-slider"
                type="range"
                min={1}
                max={3}
                value={filters.localDepth}
                onChange={(e) =>
                  handleUpdate({ localDepth: Number(e.target.value) })
                }
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
