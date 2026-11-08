// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  applyAppearance,
  createAppearanceStore,
  DEFAULT_APPEARANCE,
  parseAppearance,
} from "./appearance";

describe("parseAppearance", () => {
  it("reads a valid saved choice", () => {
    expect(parseAppearance('{"accent":"ocean","theme":"dark"}')).toEqual({
      accent: "ocean",
      theme: "dark",
    });
  });
  it("falls back for missing, malformed or unknown values", () => {
    expect(parseAppearance(null)).toEqual(DEFAULT_APPEARANCE);
    expect(parseAppearance("{not json")).toEqual(DEFAULT_APPEARANCE);
    expect(parseAppearance('"violet"')).toEqual(DEFAULT_APPEARANCE);
    expect(parseAppearance('{"accent":"neon","theme":"sepia"}')).toEqual(
      DEFAULT_APPEARANCE,
    );
  });
  it("keeps the valid half of a partly bad value", () => {
    expect(parseAppearance('{"accent":"slate","theme":42}')).toEqual({
      accent: "slate",
      theme: "system",
    });
  });
});

describe("appearance store", () => {
  it("round-trips through the injected storage", () => {
    const data = new Map<string, string>();
    const store = createAppearanceStore(() => ({
      getItem: (k) => data.get(k) ?? null,
      setItem: (k, v) => void data.set(k, v),
    }));
    store.save({ accent: "forest", theme: "light" });
    expect(store.load()).toEqual({ accent: "forest", theme: "light" });
  });
  it("degrades to defaults when storage is unavailable", () => {
    const store = createAppearanceStore(() => {
      throw new Error("SecurityError");
    });
    expect(() => store.save({ accent: "ocean", theme: "dark" })).not.toThrow();
    expect(store.load()).toEqual(DEFAULT_APPEARANCE);
  });
});

describe("applyAppearance", () => {
  it("sets the accent and forces or releases the theme", () => {
    const root = document.createElement("html");
    applyAppearance({ accent: "sunset", theme: "dark" }, root);
    expect(root.dataset).toMatchObject({ accent: "sunset", theme: "dark" });
    applyAppearance({ accent: "sunset", theme: "system" }, root);
    expect(root.dataset.theme).toBeUndefined();
  });
});

describe("gradient appearance", () => {
  it("reads saved gradients and preserves middle stops in each treatment", () => {
    expect(
      parseAppearance('{"accent":"neon-aura","theme":"light"}').accent,
    ).toBe("neon-aura");
    const root = document.createElement("html");
    applyAppearance({ accent: "visible-spectrum", theme: "light" }, root);
    for (const token of [
      "--gradient-brand",
      "--gradient-vertical",
      "--gradient-action",
      "--gradient-wash",
      "--gradient-text",
    ]) {
      expect(root.style.getPropertyValue(token)).toContain("#00ff76");
      expect(root.style.getPropertyValue(token)).toContain("#fff200");
    }
    expect(root.style.getPropertyValue("--gradient-vertical")).toContain(
      "180deg",
    );
    expect(root.dataset.gradient).toBe("true");
    applyAppearance({ accent: "violet", theme: "system" }, root);
    expect(root.dataset.gradient).toBeUndefined();
    for (const token of [
      "--gradient-brand",
      "--gradient-vertical",
      "--gradient-action",
      "--gradient-wash",
      "--gradient-text",
    ]) {
      expect(root.style.getPropertyValue(token)).toBe("");
    }
  });
});
