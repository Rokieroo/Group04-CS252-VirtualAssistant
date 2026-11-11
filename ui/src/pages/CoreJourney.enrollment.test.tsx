// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, it, expect, vi } from "vitest";
import { useState } from "react";
import { CoreJourney } from "./CoreJourney";
import type { Page } from "../navigation";
afterEach(cleanup);
it("removes a personal roadmap without adding it to the prepared catalog and retains syllabus editing", async () => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = vi.fn(function (
    this: HTMLDialogElement,
  ) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn();
  function App() {
    const [page, go] = useState<Page>("Library");
    return (
      <>
        <button onClick={() => go("Sources")}>Open prepared Library</button>
        <button onClick={() => go("Library")}>Open personal Courses</button>
        <CoreJourney page={page} go={go} mock />
      </>
    );
  }
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: /Prefer text/ }));
  await user.type(
    screen.getByRole("textbox", { name: "Syllabus text" }),
    "Personal syllabus{Enter}Week 1: Arrays{Enter}Final exam: week 1 (100%)",
  );
  await user.click(screen.getByRole("button", { name: /Continue to review/ }));
  await user.click(
    await screen.findByRole("button", { name: "Xác nhận đề cương" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Tạo roadmap →" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Xác nhận roadmap" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Xem roadmap →" }),
  );
  await user.click(screen.getByRole("button", { name: "Remove course" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(
    screen.getByRole("button", { name: "Edit course syllabus" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Remove course" }));
  await user.click(screen.getByRole("button", { name: "Remove" }));
  await user.click(
    screen.getByRole("button", { name: "Open prepared Library" }),
  );
  expect(screen.queryByText("Nội dung đã dán")).toBeNull();
  expect(screen.getByRole("heading", { name: "Getting Started" })).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "Open personal Courses" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Review your syllabus" }),
  ).toBeTruthy();
});
