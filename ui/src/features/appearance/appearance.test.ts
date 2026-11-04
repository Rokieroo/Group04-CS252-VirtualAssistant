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
      cardStyle: "standard",
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
  it("accepts a saved Canva gradient", () => {
    expect(parseAppearance('{"accent":"neon-aura","theme":"dark"}')).toEqual({
      accent: "neon-aura",
      theme: "dark",
      cardStyle: "standard",
    });
  });
  it("loads the cloudy style while older saved choices remain standard", () => {
    expect(parseAppearance('{"accent":"ocean","theme":"dark","cardStyle":"cloudy"}').cardStyle).toBe("cloudy");
    expect(parseAppearance('{"accent":"ocean","theme":"dark"}').cardStyle).toBe("standard");
    expect(parseAppearance('{"cardStyle":"unknown"}').cardStyle).toBe("standard");
  });
  it("keeps the valid half of a partly bad value", () => {
    expect(parseAppearance('{"accent":"slate","theme":42}')).toEqual({
      accent: "slate",
      theme: "system",
      cardStyle: "standard",
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
    store.save({ accent: "forest", theme: "light", cardStyle: "cloudy" });
    expect(store.load()).toEqual({ accent: "forest", theme: "light", cardStyle: "cloudy" });
  });
  it("degrades to defaults when storage is unavailable", () => {
    const store = createAppearanceStore(() => {
      throw new Error("SecurityError");
    });
    expect(() => store.save({ accent: "ocean", theme: "dark", cardStyle: "standard" })).not.toThrow();
    expect(store.load()).toEqual(DEFAULT_APPEARANCE);
  });
});

describe("applyAppearance", () => {
  it("sets the accent and forces or releases the theme", () => {
    const root = document.createElement("html");
    applyAppearance({ accent: "sunset", theme: "dark", cardStyle: "cloudy" }, root);
    expect(root.dataset.cardStyle).toBe("cloudy");
    expect(root.dataset).toMatchObject({ accent: "sunset", theme: "dark" });
    applyAppearance({ accent: "sunset", theme: "system", cardStyle: "standard" }, root);
    expect(root.dataset.cardStyle).toBeUndefined();
    expect(root.dataset.theme).toBeUndefined();
    applyAppearance({ accent: "neon-aura", theme: "light", cardStyle: "cloudy" }, root);
    expect(root.style.getPropertyValue("--gradient-display")).toContain(
      "#6500ff",
    );
    expect(root.style.getPropertyValue("--gradient-brand")).toContain(
      "#00e5ff",
    );
    expect(root.style.getPropertyValue("--gradient-brand")).toContain(
      "#d9ff00",
    );
    expect(root.style.getPropertyValue("--gradient-text-light")).toContain(
      "#00e5ff",
    );
    expect(
      root.style.getPropertyValue("--gradient-display-vertical"),
    ).toContain("180deg");
    expect(
      root.style.getPropertyValue("--gradient-display-vertical"),
    ).toContain("#00e5ff");
    expect(root.dataset.gradient).toBe("true");
    applyAppearance({ accent: "violet", theme: "light", cardStyle: "standard" }, root);
    expect(root.style.getPropertyValue("--gradient-display")).toBe("");
    expect(root.style.getPropertyValue("--gradient-display-vertical")).toBe("");
    expect(root.style.getPropertyValue("--gradient-brand")).toBe("");
    expect(root.dataset.gradient).toBeUndefined();
  });
});
