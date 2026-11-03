// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  nav,
  pageFromHash,
  pageLabels,
  pages,
  routeOf,
  useHashPage,
  type Page,
} from "./navigation";

afterEach(() => {
  location.hash = "";
});

describe("main navigation", () => {
  it("is the core loop: Courses, Roadmap, Schedule, Library (spec 1.2)", () => {
    expect(nav.map(({ page }) => pageLabels[page])).toEqual([
      "Courses",
      "Roadmap",
      "Schedule",
      "Library",
    ]);
  });

  it("keeps supplementary pages reachable by route but out of the menu", () => {
    for (const page of ["Progress", "AI Reporter", "Companion"] as Page[]) {
      expect(nav.some((item) => item.page === page)).toBe(false);
      expect(pageFromHash(`#${routeOf(page)}`, "Home")).toBe(page);
    }
  });

  it("gives every page one unique route, and old bookmarks keep their page", () => {
    expect(new Set(pages.map(routeOf)).size).toBe(pages.length);
    expect(routeOf("AI Reporter")).toBe("ai-reporter");
    expect(pageFromHash("#library", "Home")).toBe("Library");
    expect(pageLabels.Library).toBe("Courses");
  });

  it("falls back for an unknown, empty or unavailable route", () => {
    expect(pageFromHash("#nope", "Home")).toBe("Home");
    expect(pageFromHash("", "Library")).toBe("Library");
    expect(pageFromHash("#progress", "Library", ["Library", "Roadmap"])).toBe(
      "Library",
    );
  });
});

describe("useHashPage", () => {
  const core: Page[] = ["Library", "Roadmap", "Schedule"];

  it("follows the hash, sends unavailable pages to the fallback, and writes the route", () => {
    location.hash = "#roadmap";
    const { result } = renderHook(() => useHashPage("Library", core));
    expect(result.current[0]).toBe("Roadmap");

    act(() => result.current[1]("Progress"));
    expect(result.current[0]).toBe("Library");
    expect(location.hash).toBe("#library");

    act(() => result.current[1]("Schedule"));
    expect(location.hash).toBe("#schedule");
  });

  it("keeps the current page for a hash that is not a route (the skip link)", () => {
    location.hash = "#schedule";
    const { result } = renderHook(() => useHashPage("Library", core));
    act(() => {
      location.hash = "#main";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(result.current[0]).toBe("Schedule");
  });
});
