// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { GraphCanvas, type GraphNode } from "./GraphCanvas";
import {
  MINIMAP_HEIGHT,
  MINIMAP_THRESHOLD,
  MINIMAP_WIDTH,
  computeMinimapTransform,
  minimapPointToWorld,
} from "./GraphMinimap";

function makeNodes(count: number): GraphNode[] {
  return Array.from({ length: count }, (_, idx) => ({
    id: `n-${idx}`,
    title: `Node ${idx}`,
    type: idx % 7 === 0 ? "milestone" : "topic",
    week: Math.floor(idx / 5) + 1,
    status: idx % 3 === 0 ? "mastered" : "in_progress",
    x: 80 + Math.floor(idx / 5) * 180,
    y: 90 + (idx % 5) * 85,
  }));
}

let frames: Map<number, FrameRequestCallback>;
let nextFrame: number;
let translateCalls: Array<[number, number]>;

beforeEach(() => {
  frames = new Map();
  nextFrame = 0;
  translateCalls = [];
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
    frames.set(++nextFrame, fn);
    return nextFrame;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));

  const ctx = Object.fromEntries(
    [
      "clearRect",
      "save",
      "restore",
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
      "strokeRect",
      "fillText",
      "bezierCurveTo",
      "strokeText",
      "rotate",
      "setTransform",
    ].map((key) => [key, vi.fn()]),
  ) as Record<string, any>;
  ctx.translate = vi.fn((x: number, y: number) => {
    translateCalls.push([x, y]);
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as any);
  vi.spyOn(HTMLCanvasElement.prototype, "getBoundingClientRect").mockImplementation(
    function (this: HTMLCanvasElement) {
      if (this.classList.contains("graph-minimap-canvas")) {
        return {
          left: 0,
          top: 0,
          right: MINIMAP_WIDTH,
          bottom: MINIMAP_HEIGHT,
          width: MINIMAP_WIDTH,
          height: MINIMAP_HEIGHT,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        } as DOMRect;
      }
      return {
        left: 0,
        top: 0,
        right: 900,
        bottom: 600,
        width: 900,
        height: 600,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      } as DOMRect;
    },
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const flushFrame = () =>
  act(() => {
    const callbacks = [...frames.values()];
    frames.clear();
    callbacks.forEach((fn) => fn(16));
  });

describe("GraphMinimap (#108)", () => {
  it("inverts world and minimap coordinates accurately and handles empty input", () => {
    expect(computeMinimapTransform([], 168, 104)).toBeNull();
    expect(minimapPointToWorld(10, 10, [], 168, 104)).toBeNull();

    const sample = [
      { id: "1", displayX: 100, displayY: 120, radius: 18, type: "topic" as const },
      { id: "2", displayX: 900, displayY: 500, radius: 18, type: "topic" as const },
    ];
    const tf = computeMinimapTransform(sample, 168, 104);
    expect(tf).not.toBeNull();
    const wx = 750;
    const wy = 400;
    const mx = tf!.width / 2 + (wx - tf!.cx) * tf!.scale;
    const my = tf!.height / 2 + (wy - tf!.cy) * tf!.scale;
    const back = minimapPointToWorld(mx, my, sample, 168, 104);
    expect(back!.x).toBeCloseTo(wx, 5);
    expect(back!.y).toBeCloseTo(wy, 5);
  });

  it("hides below 30 nodes and renders at 30+ nodes", () => {
    const { rerender } = render(
      <GraphCanvas nodes={makeNodes(MINIMAP_THRESHOLD - 1)} edges={[]} />,
    );
    expect(screen.queryByRole("group", { name: "Bản đồ tổng quan đồ thị" })).toBeNull();

    rerender(<GraphCanvas nodes={makeNodes(MINIMAP_THRESHOLD)} edges={[]} />);
    const minimapGroup = screen.getByRole("group", {
      name: "Bản đồ tổng quan đồ thị",
    });
    expect(minimapGroup).toBeTruthy();
    expect(minimapGroup.textContent).toContain(`(${MINIMAP_THRESHOLD})`);
  });

  it("pans the main viewport when clicked and dragged", () => {
    render(<GraphCanvas nodes={makeNodes(32)} edges={[]} />);
    flushFrame();

    const miniCanvas = screen.getByTitle("Nhấn hoặc kéo để di chuyển góc nhìn");

    translateCalls = [];
    fireEvent.pointerDown(miniCanvas, {
      pointerId: 1,
      clientX: 140,
      clientY: 80,
    });
    flushFrame();
    const afterDown = [...translateCalls];
    expect(afterDown.length).toBeGreaterThan(0);

    translateCalls = [];
    fireEvent.pointerMove(miniCanvas, {
      pointerId: 1,
      clientX: 25,
      clientY: 20,
    });
    fireEvent.pointerUp(miniCanvas, { pointerId: 1 });
    flushFrame();

    expect(translateCalls.length).toBeGreaterThan(0);
    // Pan coordinates should shift significantly from right-bottom corner to left-top corner
    expect(translateCalls[0][0]).not.toEqual(afterDown[0][0]);
  });
});
