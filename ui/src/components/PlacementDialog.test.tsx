// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as placementApi from "../api/placement";
import type { PlacementState } from "../api/placement";
import { PlacementDialog } from "./PlacementDialog";

const citation = {
  source_id: "s1",
  resource_id: null,
  title: "sets.txt",
  page: 2,
  url: null,
  institution: null,
  license: "private",
};
const asking: PlacementState = {
  id: "p1",
  roadmap_id: "r1",
  status: "active",
  asked: 0,
  max_questions: 10,
  question: {
    node_id: "n1",
    title: "Sets",
    exercise: {
      id: "e1",
      type: "numeric",
      prompt: "Compute 1 + 10.",
      choices: [],
      location: "Exercise 1:",
      citation,
    },
  },
  known: [],
  unknown: [],
  skipped: [],
  total_minutes: 120,
  known_minutes: 0,
};
const finished: PlacementState = {
  ...asking,
  status: "finished",
  asked: 1,
  question: null,
  known: ["n1"],
  known_minutes: 60,
  last_attempt: { correct: true, source_answer: "11", location: "Exercise 1:", citation },
};

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("asks a cited question, marks it and reports what the roadmap skips", async () => {
  vi.spyOn(placementApi, "startPlacement").mockResolvedValue(asking);
  const answer = vi.spyOn(placementApi, "answerPlacement").mockResolvedValue(finished);
  const onFinished = vi.fn();
  const user = userEvent.setup();
  render(<PlacementDialog roadmapId="r1" onClose={() => {}} onFinished={onFinished} />);

  expect(await screen.findByText("Compute 1 + 10.")).toBeTruthy();
  // Every question shows where it comes from: its number in the source and the page.
  expect(screen.getByText(/Exercise 1: · sets\.txt · Trang 2/)).toBeTruthy();
  await user.type(screen.getByLabelText("Câu trả lời"), "11");
  await user.click(screen.getByRole("button", { name: "Trả lời" }));

  expect(answer).toHaveBeenCalledWith("p1", "e1", "11");
  expect(await screen.findByText(/lộ trình bớt 60 \/ 120 phút/)).toBeTruthy();
  expect(onFinished).toHaveBeenCalledTimes(1);
});
