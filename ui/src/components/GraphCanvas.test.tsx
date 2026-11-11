// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import {
  GraphCanvas,
  findCyclePath,
  type GraphNode,
  type GraphEdge,
} from "./GraphCanvas";

describe("findCyclePath", () => {
  it("detects self-loop", () => {
    const edges: GraphEdge[] = [];
    const path = findCyclePath(edges, "nodeA", "nodeA");
    expect(path).toEqual(["nodeA", "nodeA"]);
  });

  it("detects direct cycle A -> B when trying to add B -> A", () => {
    const edges: GraphEdge[] = [{ parent_id: "nodeA", child_id: "nodeB" }];
    const path = findCyclePath(edges, "nodeB", "nodeA");
    expect(path).toEqual(["nodeB", "nodeA", "nodeB"]);
  });

  it("detects transitive cycle A -> B -> C when trying to add C -> A", () => {
    const edges: GraphEdge[] = [
      { parent_id: "nodeA", child_id: "nodeB" },
      { parent_id: "nodeB", child_id: "nodeC" },
    ];
    const path = findCyclePath(edges, "nodeC", "nodeA");
    expect(path).toEqual(["nodeC", "nodeA", "nodeB", "nodeC"]);
  });

  it("returns null when DAG invariant is maintained", () => {
    const edges: GraphEdge[] = [{ parent_id: "nodeA", child_id: "nodeB" }];
    const path = findCyclePath(edges, "nodeB", "nodeC");
    expect(path).toBeNull();
  });
});

describe("GraphCanvas Component", () => {
  const sampleNodes: GraphNode[] = [
    {
      id: "node-1",
      title: "Hàm và Đệ quy",
      type: "topic",
      week: 1,
      status: "mastered",
      est_minutes: 60,
    },
    {
      id: "node-2",
      title: "Con trỏ và Bộ nhớ",
      type: "topic",
      week: 2,
      status: "in_progress",
      est_minutes: 90,
      sources_status: "insufficient",
    },
    {
      id: "node-3",
      title: "Kiểm tra giữa kỳ",
      type: "milestone",
      week: 3,
      status: "not_started",
      est_minutes: 120,
    },
  ];

  const sampleEdges: GraphEdge[] = [
    {
      parent_id: "node-1",
      child_id: "node-2",
      kind: "strict",
      origin: "week_order",
    },
    {
      parent_id: "node-2",
      child_id: "node-3",
      kind: "strict",
      origin: "week_order",
    },
  ];

  beforeEach(() => {
    // Mock 2D canvas context for jsdom
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      clearRect: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
      scale: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      fill: vi.fn(),
      arc: vi.fn(),
      closePath: vi.fn(),
      fillRect: vi.fn(),
      fillText: vi.fn(),
      strokeText: vi.fn(),
      bezierCurveTo: vi.fn(),
      measureText: vi.fn(() => ({ width: 40 })),
      setLineDash: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders toolbar with week and force layout options", () => {
    render(
      <GraphCanvas nodes={sampleNodes} edges={sampleEdges} layout="week" />,
    );

    expect(screen.getByText("Theo tuần")).toBeTruthy();
    expect(screen.getByText("Lực (Obsidian)")).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Knowledge Graph Canvas" }),
    ).toBeTruthy();
  });

  it("calls onLayoutModeChange when switching layout button is clicked", () => {
    const onLayoutModeChange = vi.fn();
    render(
      <GraphCanvas
        nodes={sampleNodes}
        edges={sampleEdges}
        layout="week"
        onLayoutModeChange={onLayoutModeChange}
      />,
    );

    const forceBtn = screen.getByText("Lực (Obsidian)");
    fireEvent.click(forceBtn);
    expect(onLayoutModeChange).toHaveBeenCalledWith("force");
  });

  it("displays cycle path alert when cyclePath is supplied and does not call API", () => {
    const onEdgeCreate = vi.fn();
    render(
      <GraphCanvas
        nodes={sampleNodes}
        edges={sampleEdges}
        layout="week"
        cyclePath={["node-2", "node-1", "node-2"]}
        onEdgeCreate={onEdgeCreate}
      />,
    );

    expect(
      screen.getByText(
        /Chu trình tiên quyết bị chặn: node-2 → node-1 → node-2/i,
      ),
    ).toBeTruthy();
    expect(onEdgeCreate).not.toHaveBeenCalled();
  });

  it("handles zoom controls interaction", () => {
    render(
      <GraphCanvas nodes={sampleNodes} edges={sampleEdges} layout="week" />,
    );

    const zoomInBtn = screen.getByLabelText("Phóng to");
    const zoomOutBtn = screen.getByLabelText("Thu nhỏ");
    const resetBtn = screen.getByLabelText("Đặt lại góc nhìn");

    fireEvent.click(zoomInBtn);
    expect(screen.getByText("120%")).toBeTruthy();

    fireEvent.click(zoomOutBtn);
    expect(screen.getByText("96%")).toBeTruthy();

    fireEvent.click(resetBtn);
    expect(screen.getByText("100%")).toBeTruthy();
  });
});
