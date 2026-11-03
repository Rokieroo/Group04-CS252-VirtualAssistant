// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

afterEach(cleanup);

function renderShell(go = vi.fn(), onSettings = vi.fn()) {
  render(
    <Shell
      page="Library"
      home="Library"
      go={go}
      title="Courses"
      subtitle=""
      course="CS252"
      status="Live data"
      onSettings={onSettings}
      sidebar={<button>English foundations</button>}
    >
      <p>page</p>
    </Shell>,
  );
  return { go, onSettings };
}

const drawer = () => document.getElementById("workspace-navigation")!;

it("closes the phone drawer after a tap on a sidebar extra, not only on menu items", async () => {
  renderShell();
  await userEvent.click(screen.getByRole("button", { name: "Toggle navigation" }));
  expect(drawer().className).toContain("open");
  await userEvent.click(screen.getByRole("button", { name: "English foundations" }));
  expect(drawer().className).not.toContain("open");
});

it("lists the core loop then Settings in both navigations", async () => {
  const { go, onSettings } = renderShell();
  for (const name of ["Main navigation", "Main navigation (mobile)"]) {
    const items = screen.getByRole("navigation", { name }).querySelectorAll("button");
    expect([...items].map((b) => b.textContent)).toEqual([
      "▣Courses",
      "◇Roadmap",
      "▤Schedule",
      "❒Library",
      "⚙Settings",
    ]);
  }
  await userEvent.click(
    screen.getByRole("navigation", { name: "Main navigation" }).querySelectorAll("button")[1],
  );
  expect(go).toHaveBeenCalledWith("Roadmap");
  await userEvent.click(
    screen.getByRole("navigation", { name: "Main navigation (mobile)" }).querySelectorAll("button")[4],
  );
  expect(onSettings).toHaveBeenCalled();
});
