// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TutorialCourses } from "./TutorialCourses";

beforeEach(() => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = vi.fn(function (
    this: HTMLDialogElement,
  ) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn();
});
afterEach(cleanup);
describe("Getting Started preview enrollment", () => {
  it("initializes enrolled with lessons without a syllabus check", () => {
    render(<TutorialCourses location="roadmap" mock />);
    expect(screen.getByText("Enrolled")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Add your syllabus" }),
    ).toBeTruthy();
    expect(screen.queryByText("Continue to review")).toBeNull();
  });
  it("cancellation retains enrollment", async () => {
    const user = userEvent.setup();
    render(<TutorialCourses location="roadmap" mock />);
    await user.click(
      screen.getByRole("button", { name: "Remove Getting Started" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Enrolled")).toBeTruthy();
  });
  it("removal survives navigation and remount, then permits re-enrollment", async () => {
    const user = userEvent.setup();
    const view = render(<TutorialCourses location="roadmap" mock />);
    await user.click(
      screen.getByRole("button", { name: "Remove Getting Started" }),
    );
    await user.click(screen.getByRole("button", { name: "Remove" }));
    view.rerender(<TutorialCourses location="library" mock />);
    expect(screen.getByText("Not enrolled")).toBeTruthy();
    view.unmount();
    const next = render(<TutorialCourses location="library" mock />);
    expect(screen.getByText("Not enrolled")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Enroll" }));
    next.rerender(<TutorialCourses location="roadmap" mock />);
    expect(screen.getByText("Enrolled")).toBeTruthy();
    expect(
      screen.getAllByRole("heading", { name: "Getting Started" }),
    ).toHaveLength(1);
  });
  it("keeps the prepared catalog independent from personal course data", () => {
    localStorage.setItem(
      "personal-course",
      JSON.stringify({ title: "My uploaded course", origin: "user" }),
    );
    render(<TutorialCourses location="library" mock />);
    expect(screen.queryByText("My uploaded course")).toBeNull();
  });
  it("reports undefined prepared-course editing rules", async () => {
    const user = userEvent.setup();
    render(<TutorialCourses location="roadmap" mock />);
    await user.click(
      screen.getByRole("button", { name: "Edit Getting Started" }),
    );
    expect(screen.getByText(/Editing rules for prepared courses/)).toBeTruthy();
  });
  it("does not claim live enrollment persistence or modify preview data", () => {
    render(<TutorialCourses location="library" mock={false} />);
    expect(
      (screen.getByRole("button", { name: "Enroll" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      localStorage.getItem("pathly.preview.tutorial-enrollment.v1"),
    ).toBeNull();
    expect(screen.getByText("Enrollment unavailable")).toBeTruthy();
  });
});
