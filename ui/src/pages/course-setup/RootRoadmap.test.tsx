// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RootRoadmap } from "./RootRoadmap";
import { coursePoints, rootGeometry } from "./rootGeometry";
afterEach(cleanup);
it("creates n-1 equal-area dividers and keeps every node inside its lane and parabola", () => {
  for (const count of [1, 2, 5, 12]) {
    const g = rootGeometry(count);
    expect(g.boundaries.slice(1, -1)).toHaveLength(count - 1);
    const areas = [];
    for (let i = 0; i < count; i++) {
      const lane = g.lane(i);
      let area = 0;
      const step = (lane.high - lane.low) / 3000;
      for (let j = 0; j < 3000; j++)
        area += (g.maxRadius(lane.low + (j + 0.5) * step) ** 2 / 2) * step;
      areas.push(area);
      for (const p of coursePoints(i, count, 15)) {
        const x = p.x - 84,
          y = p.y - 260,
          angle = Math.atan2(y, x);
        expect(angle).toBeGreaterThan(lane.low);
        expect(angle).toBeLessThan(lane.high);
        expect(y * y).toBeLessThanOrEqual((175 * 175 * x) / 680 + 0.01);
        expect(x).toBeLessThanOrEqual(680);
      }
    }
    expect(Math.max(...areas) / Math.min(...areas)).toBeLessThan(1.02);
  }
});
it("renders one path per actual course, keyboard details and hidden geometry by default", () => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (
    this: HTMLDialogElement,
  ) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn();
  const courses = Array.from({ length: 5 }, (_, i) => ({
    id: String(i),
    title: `Course ${i}`,
    nodes: [{ id: "a", title: `Lesson ${i}`, description: `Description ${i}` }],
  }));
  const view = render(<RootRoadmap courses={courses} />);
  expect(view.container.querySelectorAll("[data-course-path]")).toHaveLength(5);
  expect(
    screen
      .getByRole("button", { name: "Show geometry" })
      .getAttribute("aria-pressed"),
  ).toBe("false");
  fireEvent.keyDown(
    screen.getByRole("button", { name: "Course 2: Lesson 2" }),
    { key: "Enter" },
  );
  expect(screen.getByText("Description 2")).toBeTruthy();
});
