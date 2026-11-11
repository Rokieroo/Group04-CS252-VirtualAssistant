// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RootRoadmap, orderRootCourse } from "./RootRoadmap";
import { rootLayout, rootGeometry } from "./rootGeometry";
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

it("recalculates distinct radial bands and contains the entire glyph at every drag extreme", () => {
  for (const counts of [
    [0],
    [1],
    [20],
    [1, 20],
    [1, 5, 40, 0, 3],
    Array(12).fill(15),
    Array(30).fill(3),
  ]) {
    const l = rootLayout(counts),
      extent = 15,
      origin = l.geo.origin;
    counts.forEach((count, i) => {
      const lane = l.geo.lane(i);
      let previousHigh = 0;
      l.courses[i].bands.forEach((band, j) => {
        expect(band.low).toBeGreaterThan(previousHigh);
        previousHigh = band.high;
        for (const angle of [-Math.PI, 0, Math.PI])
          for (const radius of [0, 1e8]) {
            const p = l.project(i, j, { angle, radius });
            expect(p.radius - extent).toBeGreaterThan(band.low);
            expect(p.radius + extent).toBeLessThan(band.high);
            // Sample the full visible circle, not only its center.
            for (let a = 0; a < 360; a += 15) {
              const x = p.x - origin.x + extent * Math.cos((a * Math.PI) / 180);
              const y = p.y - origin.y + extent * Math.sin((a * Math.PI) / 180);
              expect(Math.atan2(y, x)).toBeGreaterThan(lane.low);
              expect(Math.atan2(y, x)).toBeLessThan(lane.high);
              expect(y * y).toBeLessThanOrEqual(
                (175 ** 2 * l.geo.scale * x) / 680 + 0.001,
              );
              expect(x).toBeLessThan(680 * l.geo.scale);
            }
          }
      });
    });
  }
  const short = rootLayout([3, 8]),
    long = rootLayout([30, 8]);
  expect(short.courses[0].bands).toHaveLength(3);
  expect(long.courses[0].bands).toHaveLength(30);
  expect(long.geo.width).toBeGreaterThan(short.geo.width);
});

it("orders prerequisites before dependents, with week and input order breaking ties, and rejects cycles", () => {
  const course = {
    id: "c",
    title: "Course",
    nodes: [
      { id: "child", title: "A child", week: 1 },
      { id: "parent", title: "Z parent", week: 2 },
      { id: "later", title: "Later", week: 3 },
    ],
    edges: [{ parent_id: "parent", child_id: "child" }],
  };
  expect(orderRootCourse(course).nodes.map((n) => n.id)).toEqual([
    "parent",
    "child",
    "later",
  ]);
  expect(
    orderRootCourse({
      ...course,
      edges: [],
      nodes: course.nodes.map((n) =>
        n.id === "child" ? { ...n, covers: ["parent"] } : n,
      ),
    }).nodes.map((n) => n.id),
  ).toEqual(["parent", "child", "later"]);
  const invalid = {
    ...course,
    edges: [...course.edges, { parent_id: "child", child_id: "parent" }],
  };
  expect(orderRootCourse(invalid).invalid).toBe(true);
  render(<RootRoadmap courses={[invalid]} />);
  expect(screen.getByRole("alert").textContent).toContain("cycle");
  expect(screen.queryByRole("button", { name: "Course: A child" })).toBeNull();
});

it("keeps narrow sectors finite beyond the area-sampling resolution", () => {
  const layout = rootLayout(Array(2000).fill(1));
  for (const i of [0, 499, 999, 1499, 1999]) {
    const p = layout.project(i, 0);
    expect(Number.isFinite(p.radius)).toBe(true);
    expect(layout.courses[i].highAngle).toBeGreaterThan(
      layout.courses[i].lowAngle,
    );
  }
  expect(rootLayout(Array(20).fill(0)).geo.scale).toBe(1);
});
