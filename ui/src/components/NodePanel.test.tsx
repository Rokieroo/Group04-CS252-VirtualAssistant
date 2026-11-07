// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NodePanel, type ExtendedNode } from "./NodePanel";
import * as materialsApi from "../api/materials";
import * as exercisesApi from "../api/exercises";
import type { Edge } from "../api/core";
import type { RoadmapNode } from "../api/types";

describe("NodePanel Component (Issue #109, Spec 8.6, 9.2, #94)", () => {
  const sampleNode: ExtendedNode = {
    id: "node-2",
    roadmap_id: "rm-1",
    title: "Binary Search Trees",
    type: "topic",
    kind: "topic",
    week: 3,
    est_minutes: 45,
    duration_minutes: 45,
    due_at: null,
    covers: [],
    status: "available",
    outcome_ids: ["CLO 1.2", "CLO 2.1"],
    syllabus_page: 15,
  };

  const allNodes: RoadmapNode[] = [
    {
      id: "node-1",
      roadmap_id: "rm-1",
      title: "Array and Linked List",
      type: "topic",
      kind: "topic",
      week: 1,
      duration_minutes: 30,
      est_minutes: 30,
      due_at: null,
      covers: [],
    },
    sampleNode,
    {
      id: "node-3",
      roadmap_id: "rm-1",
      title: "Balanced Trees (AVL)",
      type: "topic",
      kind: "topic",
      week: 4,
      duration_minutes: 60,
      est_minutes: 60,
      due_at: null,
      covers: [],
    },
  ];

  const edges: Edge[] = [
    {
      parent_id: "node-1",
      child_id: "node-2",
      kind: "strict",
      confidence: 1.0,
      origin: "week_order",
    },
    {
      parent_id: "node-2",
      child_id: "node-3",
      kind: "strict",
      confidence: 1.0,
      origin: "llm",
    },
  ];

  beforeEach(() => {
    vi.spyOn(materialsApi, "nodeSources").mockResolvedValue({
      node_id: "node-2",
      status: "ready",
      user_material_count: 1,
      sources: [
        {
          kind: "user_material",
          id: "mat-1",
          title: "Lecture 3 Slides - Trees.pdf",
          url: null,
          pages: [12, 13, 14],
          provider: "User upload",
          format: "pdf",
          reason: "Gắn bởi giảng viên môn học",
        },
        {
          kind: "catalog",
          id: "cat-1",
          title: "MIT OCW 6.006 Trees Lecture",
          url: "https://ocw.mit.edu/courses/6-006/trees",
          pages: [],
          provider: "MIT OCW",
          format: "video",
          reason: "Covers BST insertion and deletion",
        },
      ],
    });

    vi.spyOn(exercisesApi, "fetchNodeExercises").mockResolvedValue({
      node_id: "node-2",
      count: 2,
      exercises: [
        {
          id: "ex-1",
          type: "mcq",
          prompt: "What is the worst-case search time in an unbalanced BST?",
          choices: ["O(1)", "O(log n)", "O(n)", "O(n^2)"],
          citation: {
            source_id: null,
            resource_id: "cat-1",
            title: "MIT 6.006 BST Notes",
            page: 4,
            url: "https://ocw.mit.edu/6-006",
            institution: "MIT OCW",
            license: "CC-BY-4.0",
          },
        },
      ],
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders node header with week, duration, CLO chips, and syllabus page button", async () => {
    const pageSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onOpenSyllabusPage={pageSpy}
      />
    );

    expect(await screen.findByText(/Binary Search Trees/)).toBeTruthy();
    expect(screen.getByText("Tuần 3")).toBeTruthy();
    expect(screen.getByText(/45 phút/)).toBeTruthy();
    expect(screen.getByText(/CLO 1.2/)).toBeTruthy();
    expect(screen.getByText(/CLO 2.1/)).toBeTruthy();

    const syllabusChip = screen.getByRole("button", { name: /Trang syllabus: 15/i });
    fireEvent.click(syllabusChip);
    expect(pageSpy).toHaveBeenCalledWith(15);
  });

  it("updates URL hash to #roadmaps/{id}/graph/{node} for shareability", async () => {
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(window.location.hash).toBe("#roadmaps/rm-1/graph/node-2");
    });
  });

  it("closes panel on Escape key or close button", async () => {
    const closeSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={closeSpy}
      />
    );

    // Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeSpy).toHaveBeenCalled();

    // Close button
    fireEvent.click(screen.getByRole("button", { name: /Đóng bảng thông tin chặng/i }));
    expect(closeSpy).toHaveBeenCalledTimes(2);
  });

  it("shows prerequisites and unlocks, allowing one-click navigation", async () => {
    const selectSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onSelectNode={selectSpy}
      />
    );

    const prereqBtn = await screen.findByRole("button", { name: /← Array and Linked List/i });
    fireEvent.click(prereqBtn);
    expect(selectSpy).toHaveBeenCalledWith("node-1");

    const unlockBtn = screen.getByRole("button", { name: /→ Balanced Trees \(AVL\)/i });
    fireEvent.click(unlockBtn);
    expect(selectSpy).toHaveBeenCalledWith("node-3");
  });

  it("highlights learning path when 'Đường học tới đây' is clicked", async () => {
    const pathSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onHighlightPath={pathSpy}
      />
    );

    const pathBtn = await screen.findByRole("button", { name: /Đường học tới đây/i });
    fireEvent.click(pathBtn);

    expect(pathSpy).toHaveBeenCalledWith(expect.arrayContaining(["node-2", "node-1"]));
  });

  it("prioritizes user materials over catalog sources and provides page action", async () => {
    const matPageSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onOpenMaterialPage={matPageSpy}
      />
    );

    // User material
    expect(await screen.findByText(/Lecture 3 Slides - Trees.pdf/)).toBeTruthy();
    const pageBtn = screen.getByRole("button", { name: /Trang 12/i });
    fireEvent.click(pageBtn);
    expect(matPageSpy).toHaveBeenCalledWith("mat-1", 12);

    // Catalog source with domain and safe link
    const link = screen.getByRole("link", { name: /MIT OCW 6.006 Trees Lecture/i });
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.getByText("ocw.mit.edu")).toBeTruthy();
  });

  it("displays exact spec text 'Chưa tìm được nguồn đủ tốt' when status is insufficient", async () => {
    vi.spyOn(materialsApi, "nodeSources").mockResolvedValue({
      node_id: "node-2",
      status: "insufficient",
      user_material_count: 0,
      sources: [],
    });

    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(await screen.findByText("Chưa tìm được nguồn đủ tốt")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tìm lại" })).toBeTruthy();
  });

  it("displays exercises preview with citation chips and practice gateway", async () => {
    const practiceSpy = vi.fn();
    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onOpenPractice={practiceSpy}
      />
    );

    expect(await screen.findByText(/worst-case search time/)).toBeTruthy();
    expect(screen.getByText(/MIT OCW · Trang 4/)).toBeTruthy();

    const practiceBtn = screen.getByRole("button", { name: /Luyện tập chặng này/i });
    fireEvent.click(practiceBtn);
    expect(practiceSpy).toHaveBeenCalledWith("node-2", ["ex-1"]);
  });

  it("provides gateways to S6 Stage Page, S10 Ask AI, and S7 Schedule", async () => {
    const stageSpy = vi.fn();
    const askSpy = vi.fn();
    const schedSpy = vi.fn();

    render(
      <NodePanel
        roadmapId="rm-1"
        node={sampleNode}
        allNodes={allNodes}
        edges={edges}
        isOpen={true}
        onClose={vi.fn()}
        onOpenFullStage={stageSpy}
        onAskQuestion={askSpy}
        onScheduleNode={schedSpy}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: /Trang chặng \(S6\)/i }));
    expect(stageSpy).toHaveBeenCalledWith("node-2");

    fireEvent.click(screen.getByRole("button", { name: /Hỏi đáp AI \(S10\)/i }));
    expect(askSpy).toHaveBeenCalledWith("node-2");

    fireEvent.click(screen.getByRole("button", { name: /Xếp vào lịch \(S7\)/i }));
    expect(schedSpy).toHaveBeenCalledWith("node-2");
  });
});
