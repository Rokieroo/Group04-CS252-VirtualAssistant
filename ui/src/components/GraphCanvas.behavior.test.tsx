// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  act,
} from "@testing-library/react";
import { GraphCanvas } from "./GraphCanvas";
import { BackendError } from "../api/backend";
let frames: Map<number, FrameRequestCallback>;
let next: number;
let ctx: Record<string, any>;
let fillColors: string[];
const nodes = [
  { id: "a", title: "A", type: "topic" as const, week: 1 },
  { id: "b", title: "B", type: "topic" as const, week: 2 },
];
beforeEach(() => {
  frames = new Map();
  next = 0;
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
    frames.set(++next, fn);
    return next;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  ctx = Object.fromEntries(
    [
      "clearRect",
      "save",
      "restore",
      "translate",
      "scale",
      "beginPath",
      "moveTo",
      "lineTo",
      "stroke",
      "setLineDash",
      "closePath",
      "fill",
      "arc",
      "fillRect",
      "fillText",
    ].map((key) => [key, vi.fn()]),
  );
  fillColors = [];
  Object.defineProperty(ctx, "fillStyle", {
    set: (color: string) => fillColors.push(color),
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as any,
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function frame() {
  act(() => {
    const callbacks = [...frames.values()];
    frames.clear();
    callbacks.forEach((fn) => fn(0));
  });
}
it("draws with the latest zoom and pan rather than stale render state", () => {
  render(<GraphCanvas nodes={nodes} edges={[]} />);
  frame();
  fireEvent.click(screen.getByLabelText("Phóng to"));
  frame();
  expect(ctx.scale).toHaveBeenLastCalledWith(1.2, 1.2);
  fireEvent.keyDown(screen.getByRole("region"), { key: "ArrowRight" });
  frame();
  expect(ctx.translate).toHaveBeenLastCalledWith(20, 60);
});
it("blocks a cycle using full graph even when those edges are hidden", async () => {
  const create = vi.fn();
  const view = render(
    <GraphCanvas
      nodes={nodes}
      edges={[]}
      cycleEdges={[{ parent_id: "a", child_id: "b" }]}
      onEdgeCreate={create}
    />,
  );
  const canvas = view.container.querySelector("canvas")!;
  fireEvent.pointerDown(canvas, { clientX: 320, clientY: 140, shiftKey: true });
  fireEvent.pointerUp(canvas, { clientX: 140, clientY: 140 });
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).toContain("b → a → b");
  expect(create).not.toHaveBeenCalled();
  frame();
  expect(fillColors).toContain("#ef4444");
});
it("shows structured server cycle paths", async () => {
  const create = vi
    .fn()
    .mockRejectedValue(
      new BackendError(409, "conflict", { path: ["a", "b", "a"] }),
    );
  const view = render(
    <GraphCanvas nodes={nodes} edges={[]} onEdgeCreate={create} />,
  );
  const canvas = view.container.querySelector("canvas")!;
  fireEvent.pointerDown(canvas, { clientX: 140, clientY: 140, shiftKey: true });
  fireEvent.pointerUp(canvas, { clientX: 320, clientY: 140 });
  expect((await screen.findByRole("alert")).textContent).toContain("a → b → a");
});

it("debounces drag persistence without opening the node panel mid-drag", () => {
  vi.useFakeTimers();
  const persist = vi.fn(),
    select = vi.fn();
  const view = render(
    <GraphCanvas
      nodes={nodes}
      edges={[]}
      onSelect={select}
      onLayoutChange={persist}
    />,
  );
  const canvas = view.container.querySelector("canvas")!;
  fireEvent.pointerDown(canvas, { clientX: 140, clientY: 140 });
  fireEvent.pointerMove(canvas, { clientX: 190, clientY: 180 });
  fireEvent.pointerUp(canvas, { clientX: 190, clientY: 180 });
  expect(select).not.toHaveBeenCalled();
  expect(persist).not.toHaveBeenCalled();
  act(() => vi.advanceTimersByTime(1000));
  expect(persist).toHaveBeenCalledWith(
    expect.arrayContaining([
      expect.objectContaining({ node_id: "a", x: 130, y: 120, pinned: true }),
    ]),
  );
  vi.useRealTimers();
});
it("restores week positions for unpinned nodes after force layout", () => {
  const view = render(<GraphCanvas nodes={nodes} edges={[]} layout="week" />);
  view.rerender(<GraphCanvas nodes={nodes} edges={[]} layout="force" />);
  frame();
  view.rerender(<GraphCanvas nodes={nodes} edges={[]} layout="week" />);
  ctx.arc.mockClear();
  frame();
  expect(
    ctx.arc.mock.calls.some((c: number[]) => c[0] === 80 && c[1] === 80),
  ).toBe(true);
});
