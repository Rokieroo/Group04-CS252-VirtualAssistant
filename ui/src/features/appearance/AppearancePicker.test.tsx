// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppearanceStore } from "./appearance";
import { AppearancePicker } from "./AppearancePicker";

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.accent;
  delete document.documentElement.dataset.theme;
});

function setup() {
  const store: AppearanceStore = {
    load: () => ({ accent: "violet", theme: "system" }),
    save: vi.fn(),
  };
  render(<AppearancePicker store={store} />);
  return store;
}

describe("appearance picker", () => {
  it("starts from the stored choice", () => {
    setup();
    expect(
      (screen.getByRole("radio", { name: "Violet" }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: "Match device" }) as HTMLInputElement)
        .checked,
    ).toBe(true);
  });
  it("applies and saves an accent and a theme as soon as they are picked", async () => {
    const user = userEvent.setup();
    const store = setup();
    await user.click(screen.getByRole("radio", { name: "Ocean" }));
    await user.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.dataset).toMatchObject({
      accent: "ocean",
      theme: "dark",
    });
    expect(store.save).toHaveBeenLastCalledWith({
      accent: "ocean",
      theme: "dark",
    });
    await user.click(screen.getByRole("radio", { name: "Windy" }));
    expect(document.documentElement.dataset).toMatchObject({
      accent: "ocean",
      theme: "windy",
    });
    expect(store.save).toHaveBeenLastCalledWith({
      accent: "ocean",
      theme: "windy",
    });
    await user.click(screen.getByRole("radio", { name: "Flame" }));
    expect(document.documentElement.dataset).toMatchObject({
      accent: "ocean",
      theme: "flame",
    });
    expect(store.save).toHaveBeenLastCalledWith({
      accent: "ocean",
      theme: "flame",
    });
  });
});
