// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { GraphFilterBar, type FilterState } from "./GraphFilterBar";

describe("GraphFilterBar Component", () => {
  const initialFilters: FilterState = {
    search: "",
    weekMin: 1,
    weekMax: 15,
    status: "all",
    clo: "",
    verifiedOnly: false,
    hideSoftEdges: false,
    transitiveReduction: false,
    selectedMilestone: "",
    isLocalGraph: false,
    localDepth: 2,
    viewMode: "graph",
  };

  const sampleNodes = [
    {
      id: "node-1",
      title: "Cấu trúc dữ liệu và Giải thuật",
      type: "topic" as const,
      week: 1,
      status: "mastered",
      clo: ["CLO 1.1"],
      sources_status: "sufficient",
    },
    {
      id: "node-2",
      title: "Độ phức tạp tính toán Big-O",
      type: "topic" as const,
      week: 2,
      status: "in_progress",
      clo: ["CLO 1.2"],
      sources_status: "insufficient",
    },
    {
      id: "node-m1",
      title: "Kiểm tra giữa kỳ",
      type: "milestone" as const,
      week: 7,
      status: "not_started",
    },
  ];

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders search input, milestone dropdown, and view mode toggles", () => {
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={initialFilters}
        onChange={vi.fn()}
        onSelectNode={vi.fn()}
      />,
    );

    expect(screen.getByPlaceholderText("Tìm chủ đề chặng học...")).toBeTruthy();
    expect(screen.getByLabelText("Tới mốc kiểm tra:")).toBeTruthy();
    expect(screen.getByText("Đồ thị")).toBeTruthy();
    expect(screen.getByText("Danh sách")).toBeTruthy();
  });

  it("triggers suggestions when typing in search input", () => {
    const onChange = vi.fn();
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={{ ...initialFilters, search: "Cấu trúc" }}
        onChange={onChange}
        onSelectNode={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText("Tìm chủ đề chặng học...");
    fireEvent.focus(input);

    expect(screen.getByText("Cấu trúc dữ liệu và Giải thuật")).toBeTruthy();
  });

  it("selects suggestion and triggers onSelectNode", () => {
    const onSelectNode = vi.fn();
    const onChange = vi.fn();
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={{ ...initialFilters, search: "Big-O" }}
        onChange={onChange}
        onSelectNode={onSelectNode}
      />,
    );

    const input = screen.getByPlaceholderText("Tìm chủ đề chặng học...");
    fireEvent.focus(input);

    const suggestion = screen.getByText("Độ phức tạp tính toán Big-O");
    fireEvent.mouseDown(suggestion);

    expect(onSelectNode).toHaveBeenCalledWith("node-2");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ search: "Độ phức tạp tính toán Big-O" }),
    );
  });

  it("toggles viewMode between graph and list", () => {
    const onChange = vi.fn();
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={initialFilters}
        onChange={onChange}
        onSelectNode={vi.fn()}
      />,
    );

    const listBtn = screen.getByText("Danh sách");
    fireEvent.click(listBtn);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ viewMode: "list" }),
    );
  });

  it("focuses search input when global '/' key is pressed", () => {
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={initialFilters}
        onChange={vi.fn()}
        onSelectNode={vi.fn()}
      />,
    );

    const searchInput = screen.getByPlaceholderText("Tìm chủ đề chặng học...");
    expect(document.activeElement).not.toBe(searchInput);

    fireEvent.keyDown(window, { key: "/" });
    expect(document.activeElement).toBe(searchInput);
  });
  it("keeps milestone access visible and hides secondary controls until requested", () => {
    const changed = vi.fn();
    render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={initialFilters}
        onChange={changed}
        onSelectNode={vi.fn()}
      />,
    );
    const toggle = screen.getByRole("button", { name: "Bộ lọc (1)" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("combobox", { name: "Trạng thái:" })).toBeNull();
    expect(
      screen.getByRole("combobox", { name: "Tới mốc kiểm tra:" }),
    ).toBeTruthy();
    expect(screen.getByText("Tuần 1–15").textContent).toBe("Tuần 1–15");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.change(screen.getByRole("combobox", { name: "Trạng thái:" }), {
      target: { value: "mastered" },
    });
    expect(changed).toHaveBeenCalledWith(
      expect.objectContaining({ status: "mastered" }),
    );
    fireEvent.click(toggle);
    expect(screen.queryByRole("combobox", { name: "Trạng thái:" })).toBeNull();
  });

  it("counts a week range once and local depth only while enabled; clearing preserves the view", () => {
    const changed = vi.fn();
    const filters: FilterState = {
      ...initialFilters,
      search: "topic",
      selectedMilestone: "node-m1",
      status: "mastered",
      viewMode: "list",
      localDepth: 3,
    };
    const { rerender } = render(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={filters}
        onChange={changed}
        onSelectNode={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Bộ lọc (2)" })).toBeTruthy();
    rerender(
      <GraphFilterBar
        nodes={sampleNodes}
        filters={{ ...filters, isLocalGraph: true }}
        onChange={changed}
        onSelectNode={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Bộ lọc (3)" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ lọc" }));
    expect(changed).toHaveBeenLastCalledWith({
      search: "",
      selectedMilestone: "",
      status: "all",
      clo: "",
      weekMin: 1,
      weekMax: 52,
      verifiedOnly: false,
      hideSoftEdges: false,
      transitiveReduction: false,
      isLocalGraph: false,
      localDepth: 2,
      viewMode: "list",
    });
  });
});
