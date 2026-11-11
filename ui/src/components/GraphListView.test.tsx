// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { GraphListView, type GraphListNode } from "./GraphListView";

describe("GraphListView Component (Accessible List Mode)", () => {
  const sampleNodes: GraphListNode[] = [
    {
      id: "node-1",
      title: "Cấu trúc dữ liệu mảng và danh sách",
      type: "topic",
      week: 1,
      status: "mastered",
      sources_count: 3,
      sources_status: "sufficient",
      clo: ["CLO 1.1"],
      est_minutes: 45,
    },
    {
      id: "node-2",
      title: "Hàng đợi ưu tiên và Heap",
      type: "topic",
      week: 3,
      status: "review_due",
      sources_count: 1,
      sources_status: "insufficient",
      clo: ["CLO 2.1"],
      est_minutes: 60,
    },
    {
      id: "node-m1",
      title: "Thi thực hành tuần 5",
      type: "milestone",
      week: 5,
      status: "not_started",
      sources_count: 2,
    },
  ];

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders accessible table with semantic headers and caption", () => {
    render(<GraphListView nodes={sampleNodes} onSelect={vi.fn()} />);

    expect(
      screen.getByRole("region", { name: "Danh sách chặng học tiếp cận" }),
    ).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("Tuần")).toBeTruthy();
    expect(screen.getByText("Chặng học")).toBeTruthy();
    expect(screen.getByText("Trạng thái")).toBeTruthy();
  });

  it("renders rows with proper badges, weeks and statuses", () => {
    render(<GraphListView nodes={sampleNodes} onSelect={vi.fn()} />);

    expect(screen.getByText("Cấu trúc dữ liệu mảng và danh sách")).toBeTruthy();
    expect(screen.getByText("Hàng đợi ưu tiên và Heap")).toBeTruthy();
    expect(screen.getByText("Thi thực hành tuần 5")).toBeTruthy();

    expect(screen.getByText("Đã vững")).toBeTruthy();
    expect(screen.getByText("Cần ôn tập")).toBeTruthy();
    expect(screen.getByText("Chưa học")).toBeTruthy();

    expect(screen.getByText("✓ 3 nguồn")).toBeTruthy();
    expect(screen.getByText("⚠️ Chưa đủ")).toBeTruthy();
  });

  it("calls onSelect when row or detail button is clicked", () => {
    const onSelect = vi.fn();
    render(<GraphListView nodes={sampleNodes} onSelect={onSelect} />);

    const topicBtn = screen.getByLabelText(
      "Chọn chặng Cấu trúc dữ liệu mảng và danh sách",
    );
    fireEvent.click(topicBtn);
    expect(onSelect).toHaveBeenCalledWith("node-1");

    const detailButtons = screen.getAllByText("Chi tiết");
    fireEvent.click(detailButtons[1]);
    expect(onSelect).toHaveBeenCalledWith("node-2");
  });

  it("highlights selected row", () => {
    render(
      <GraphListView
        nodes={sampleNodes}
        selectedId="node-2"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Đang chọn")).toBeTruthy();
    const rows = screen.getAllByRole("row");
    // Row 0 is header, Row 2 is node-2
    expect(rows[2].getAttribute("aria-selected")).toBe("true");
  });
  it("does not label personal materials as verified catalog sources", () => {
    render(
      <GraphListView
        nodes={[
          {
            ...sampleNodes[0],
            id: "private",
            sources_count: 2,
            verified_sources_count: 0,
            sources_status: "sufficient",
          },
          {
            ...sampleNodes[1],
            id: "mixed",
            sources_count: 4,
            verified_sources_count: 2,
            sources_status: "sufficient",
          },
        ]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/0 nguồn đã xác minh/)).toBeTruthy();
    expect(screen.getByText("✓ 2 nguồn")).toBeTruthy();
    expect(screen.queryByText("✓ 4 nguồn")).toBeNull();
  });
  it("does not turn pending source checks into an insufficient verdict", () => {
    render(
      <GraphListView
        nodes={[
          {
            ...sampleNodes[0],
            status: undefined,
            sources_status: "pending",
            verified_sources_count: 0,
            sources_count: 0,
          },
        ]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Đang kiểm tra")).toBeTruthy();
    expect(screen.queryByText(/0 nguồn đã xác minh/)).toBeNull();
    expect(screen.getByText("Chưa có trạng thái")).toBeTruthy();
  });
});
