// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TodayPage } from "./TodayPage";
import * as reviewsApi from "../api/reviews";
import type { RoadmapNode } from "../api/types";

describe("TodayPage component (Issue #159, UC-11, Spec 8)", () => {
  const sampleNodes: RoadmapNode[] = [
    {
      id: "node-topic-1",
      roadmap_id: "rm-1",
      title: "Binary Search Trees",
      type: "topic",
      kind: "topic",
      week: 2,
      duration_minutes: 45,
      est_minutes: 45,
      due_at: "2026-11-12T10:00:00Z",
      covers: [],
    },
    {
      id: "node-milestone-1",
      roadmap_id: "rm-1",
      title: "Midterm Exam",
      type: "milestone",
      kind: "milestone",
      week: 4,
      duration_minutes: 90,
      est_minutes: 90,
      due_at: "2026-11-20T10:00:00Z",
      covers: ["node-topic-1"],
    },
  ];

  beforeEach(() => {
    vi.spyOn(reviewsApi, "fetchDueReviews").mockResolvedValue([
      {
        item_id: "item-1",
        user_id: "user-1",
        node_id: "node-topic-1",
        due_at: "2026-11-12T08:00:00Z",
        stability: 2.5,
        difficulty: 2.1,
        state: 1,
        step: 1,
        last_review: "2026-11-11T08:00:00Z",
        prompt: "What is the worst-case lookup time in an unbalanced BST?",
        choices: ["O(1)", "O(log n)", "O(n)"],
        type: "mcq",
        source_id: "src-1",
      },
    ]);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders today screen with date, metrics, due topics, reviews, and milestones", async () => {
    const goSpy = vi.fn();
    const openNodeSpy = vi.fn();

    render(
      <TodayPage
        go={goSpy}
        onOpenNodeOnGraph={openNodeSpy}
        roadmapId="rm-1"
        nodes={sampleNodes}
      />,
    );

    // Title & date
    expect(await screen.findByRole("heading", { name: "Today" })).toBeTruthy();

    // Metrics summary
    expect(screen.getByText("Stages to study")).toBeTruthy();
    expect(screen.getByText("FSRS reviews")).toBeTruthy();
    expect(screen.getByText("Milestones")).toBeTruthy();

    // Due topic
    expect(screen.getByText("Binary Search Trees")).toBeTruthy();
    expect(screen.getByText("Week 2")).toBeTruthy();

    // Due FSRS review
    expect(screen.getByText(/worst-case lookup time/)).toBeTruthy();

    // Upcoming Milestone
    expect(screen.getByText(/Midterm Exam/)).toBeTruthy();

    // Test clicking "Open on Graph →" opens the node on the graph
    const openTopicBtn = screen.getByRole("button", {
      name: /Open stage Binary Search Trees on Knowledge Graph/i,
    });
    fireEvent.click(openTopicBtn);
    expect(openNodeSpy).toHaveBeenCalledWith("node-topic-1", "rm-1");
  });

  it("renders graceful empty state when there are no due topics or reviews", async () => {
    vi.spyOn(reviewsApi, "fetchDueReviews").mockResolvedValue([]);

    render(
      <TodayPage
        go={vi.fn()}
        roadmapId="rm-1"
        nodes={[]}
      />,
    );

    expect(
      await screen.findByText(/You have no overdue learning stages today/),
    ).toBeTruthy();
    expect(
      screen.getByText(/You have completed all FSRS review cards due today/),
    ).toBeTruthy();
    expect(
      screen.getByText(/No upcoming exams or milestones/),
    ).toBeTruthy();
  });

  it("handles review load failure gracefully without crashing the UI", async () => {
    vi.spyOn(reviewsApi, "fetchDueReviews").mockRejectedValue(new Error("Network failed"));

    render(
      <TodayPage
        go={vi.fn()}
        roadmapId="rm-1"
        nodes={sampleNodes}
      />,
    );

    // Header and topics still render fine
    expect(await screen.findByRole("heading", { name: "Today" })).toBeTruthy();
    expect(screen.getByText("Binary Search Trees")).toBeTruthy();
  });

  it("ignores late review responses that resolve after unmount", async () => {
    let resolvePending: (cards: Awaited<ReturnType<typeof reviewsApi.fetchDueReviews>>) => void =
      () => {};
    vi.spyOn(reviewsApi, "fetchDueReviews").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePending = resolve;
        }),
    );

    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = render(
      <TodayPage go={vi.fn()} roadmapId="rm-1" nodes={sampleNodes} />,
    );

    unmount();
    resolvePending([]);
    await Promise.resolve();

    expect(errorSpy).not.toHaveBeenCalled();
  });
});
