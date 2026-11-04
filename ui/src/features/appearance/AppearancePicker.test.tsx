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
  delete document.documentElement.dataset.cardStyle;
});

function setup() {
  const store: AppearanceStore = {
    load: () => ({ accent: "violet", theme: "system", cardStyle: "standard" }),
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
    expect((screen.getByRole("radio", { name: "Standard" }) as HTMLInputElement).checked).toBe(true);
  });
  it("offers a Canva gradient and applies it immediately", async () => {
    const user = userEvent.setup();
    const store = setup();
    await user.click(screen.getByRole("radio", { name: "Neon Aura" }));
    expect(document.documentElement.dataset.accent).toBe("neon-aura");
    expect(document.documentElement.style.getPropertyValue("--gradient-display")).toContain("#6500ff");
    expect(store.save).toHaveBeenCalledWith({ accent: "neon-aura", theme: "system", cardStyle: "standard" });
  });
  it("switches card style immediately and saves the choice", async () => {
    const user = userEvent.setup();
    const store = setup();
    await user.click(screen.getByRole("radio", { name: "Cloudy" }));
    expect(document.documentElement.dataset.cardStyle).toBe("cloudy");
    expect(store.save).toHaveBeenLastCalledWith({ accent: "violet", theme: "system", cardStyle: "cloudy" });
    await user.click(screen.getByRole("radio", { name: "Standard" }));
    expect(document.documentElement.dataset.cardStyle).toBeUndefined();
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
      cardStyle: "standard",
    });
  });
});
