// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  act,
} from "@testing-library/react";
import { GRAPH_FALLBACK, GraphCanvas } from "./GraphCanvas";
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
  const canvasMethodNames = [
    "clearRect",
    "save",
    "restore",
    "setTransform",
    "translate",
    "scale",
    "rotate",
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
  ];
  const makeMockCtx = (): Record<string, any> => {
    const mock: Record<string, any> = Object.fromEntries(
      canvasMethodNames.map((key) => [key, vi.fn()]),
    );
    mock.measureText = vi.fn((text: string) => ({ width: text.length * 7 }));
    mock.font = "12px sans-serif";
    mock.textAlign = "center";
    mock.textBaseline = "middle";
    return mock;
  };
  ctx = makeMockCtx();
  const minimapCtx = makeMockCtx();
  fillColors = [];
  let currentFill = "";
  Object.defineProperty(ctx, "fillStyle", {
    get: () => currentFill,
    set: (color: string) => {
      currentFill = color;
      fillColors.push(color);
    },
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    function (this: HTMLCanvasElement) {
      return (
        this.classList?.contains("graph-minimap-canvas") ? minimapCtx : ctx
      ) as any;
    },
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
  fireEvent.click(screen.getByLabelText("Zoom in"));
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
  expect(fillColors).toContain(GRAPH_FALLBACK.danger);
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
  // Nodes glide back over several frames; the last moving frame lands exactly.
  for (let i = 0; i < 60; i++) frame();
  expect(
    ctx.arc.mock.calls.some((c: number[]) => c[0] === 80 && c[1] === 80),
  ).toBe(true);
});

it("wheel zoom glides around the cursor and an idle graph schedules no requestAnimationFrame", () => {
  const view = render(<GraphCanvas nodes={nodes} edges={[]} />);
  frame();
  // Idle graph stops scheduling animation frames completely.
  expect(frames.size).toBe(0);
  // jsdom puts the canvas at 0,0: the world point under (100, 100) is (40, 40) at zoom 1.
  fireEvent.wheel(view.container.querySelector("canvas")!, {
    deltaY: -100,
    clientX: 100,
    clientY: 100,
  });
  expect(frames.size).toBeGreaterThan(0);
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeLessThan(1.1);
  for (let i = 0; i < 60 && frames.size > 0; i++) frame();
  expect(frames.size).toBe(0);
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(1.1);
  expect(ctx.translate.mock.lastCall[0]).toBeCloseTo(100 - 40 * 1.1);
  expect(ctx.translate.mock.lastCall[1]).toBeCloseTo(100 - 40 * 1.1);
  ctx.clearRect.mockClear();
  for (let i = 0; i < 5; i++) frame();
  expect(ctx.clearRect).not.toHaveBeenCalled();
  expect(frames.size).toBe(0);
});

it("prefers-reduced-motion snaps view and layout transitions in one frame without looping", () => {
  let changeListener: ((e: MediaQueryListEvent) => void) | undefined;
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)",
    media: query,
    onchange: null,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => {
      if (query === "(prefers-reduced-motion: reduce)") changeListener = cb;
    },
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));

  const view = render(<GraphCanvas nodes={nodes} edges={[]} layout="week" />);
  frame();
  expect(frames.size).toBe(0);

  // Wheel zoom completes immediately in one animation step instead of easing over 20+ frames.
  fireEvent.wheel(view.container.querySelector("canvas")!, {
    deltaY: -100,
    clientX: 100,
    clientY: 100,
  });
  frame(); // view step snaps to goal zoom & pan and clears viewFrame
  frame(); // redraw tick paints snapped view and goes idle
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(1.1);
  expect(frames.size).toBe(0);

  // Layout transition from force back to week snaps without multi-frame glide when reduced motion is active.
  view.rerender(<GraphCanvas nodes={nodes} edges={[]} layout="force" />);
  frame();
  view.rerender(<GraphCanvas nodes={nodes} edges={[]} layout="week" />);
  ctx.arc.mockClear();
  frame();
  expect(
    ctx.arc.mock.calls.some((c: number[]) => c[0] === 80 && c[1] === 80),
  ).toBe(true);
  expect(frames.size).toBe(0);
  expect(changeListener).toBeTypeOf("function");
});

it("fits 32 CSC10014 concepts across 10 weeks without label overlap and renders minimap", () => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 1200,
    height: 580,
    left: 0,
    top: 0,
    right: 1200,
    bottom: 580,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);

  const stack: Array<{ tx: number; ty: number; sx: number; sy: number }> = [];
  let state = { tx: 0, ty: 0, sx: 1, sy: 1 };
  const drawnLabels: Array<{
    text: string;
    left: number;
    right: number;
    top: number;
    bottom: number;
  }> = [];

  ctx.clearRect.mockImplementation(() => {
    drawnLabels.length = 0;
  });
  ctx.save.mockImplementation(() => {
    stack.push({ ...state });
  });
  ctx.restore.mockImplementation(() => {
    state = stack.pop() ?? { tx: 0, ty: 0, sx: 1, sy: 1 };
  });
  ctx.setTransform.mockImplementation((a: number, _b: number, _c: number, d: number, e: number, f: number) => {
    state = { tx: e, ty: f, sx: a, sy: d };
  });
  ctx.translate.mockImplementation((dx: number, dy: number) => {
    state = { ...state, tx: state.tx + dx * state.sx, ty: state.ty + dy * state.sy };
  });
  ctx.scale.mockImplementation((sx: number, sy: number) => {
    state = { ...state, sx: state.sx * sx, sy: state.sy * sy };
  });
  ctx.fillText.mockImplementation((text: string, x: number, y: number) => {
    if (!text || /^WEEK\s/i.test(text)) return;
    const match = /(\d+(?:\.\d+)?)px/.exec(String(ctx.font || "12px"));
    const fontPx = match ? Number(match[1]) : 12;
    const w = ctx.measureText(text).width * state.sx;
    const h = fontPx * state.sy;
    const sx = state.tx + x * state.sx;
    const sy = state.ty + y * state.sy;
    const left = ctx.textAlign === "left" ? sx : ctx.textAlign === "right" ? sx - w : sx - w / 2;
    const top = ctx.textBaseline === "top" ? sy : ctx.textBaseline === "middle" ? sy - h / 2 : sy - h * 0.8;
    drawnLabels.push({ text, left, right: left + w, top, bottom: top + h });
  });

  const cscNodes = Array.from({ length: 32 }, (_, i) => ({
    id: `csc-${i + 1}`,
    title: [
      "Framing ladder", "Problem statement", "Stakeholder mapping", "Personas",
      "Jobs-to-be-Done", "Four layers of a need", "FR vs NFR", "Non-goals",
      "Solution ladder", "Four product risks", "Use case diagrams", "User stories",
      "Acceptance criteria", "Prioritising with MoSCoW", "Decomposition", "Pattern recognition",
      "Abstraction layers", "Algorithm design", "Flowcharts and pseudocode", "Midterm checkpoint",
      "Trade-off analysis", "Prototyping", "Usability testing", "Measuring success",
      "Data-driven decisions", "Ethics in design", "Team roles", "Iteration planning",
      "Risk register", "Final presentation", "Retrospective", "Final exam",
    ][i],
    mastery: (i % 5) * 0.25,
    confidence: i % 4 === 0 ? ("insufficient" as const) : ("high" as const),
    week: (i % 10) + 1,
    type: i % 8 === 7 ? ("milestone" as const) : ("topic" as const),
  }));
  const cscEdges = Array.from({ length: 31 }, (_, i) => ({
    parent_id: `csc-${i + 1}`,
    child_id: `csc-${i + 2}`,
  }));

  const view = render(<GraphCanvas nodes={cscNodes} edges={cscEdges} />);
  frame();
  frame();

  expect(view.container.textContent).toContain("Overview (32)");
  // Labels that would collide are skipped by design, so "no overlap" alone is free:
  // the graph is only readable at fit zoom if every concept keeps its label.
  expect(drawnLabels.map((l) => l.text).sort()).toEqual(
    cscNodes.map((n) => n.title).sort(),
  );

  for (let i = 0; i < drawnLabels.length; i += 1) {
    for (let j = i + 1; j < drawnLabels.length; j += 1) {
      const a = drawnLabels[i];
      const b = drawnLabels[j];
      const overlaps =
        a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      expect(overlaps, `Labels overlap: ${a.text} vs ${b.text}`).toBe(false);
    }
  }
});

it("uses at most 3 semantic hues beyond background/neutral and explains each in the legend", () => {
  const strokeColors: string[] = [];
  let currentStroke = "";
  Object.defineProperty(ctx, "strokeStyle", {
    get: () => currentStroke,
    set: (color: string) => {
      currentStroke = color;
      strokeColors.push(color);
    },
  });

  const allStateNodes = [
    { id: "n1", title: "Topic", type: "topic" as const, week: 1, status: "not_started" as const },
    { id: "n2", title: "Locked", type: "topic" as const, week: 1, status: "locked" as const },
    { id: "n3", title: "Available", type: "topic" as const, week: 2, status: "available" as const },
    { id: "n4", title: "Active", type: "topic" as const, week: 2, status: "in_progress" as const },
    { id: "n5", title: "Mastered", type: "topic" as const, week: 3, status: "mastered" as const },
    {
      id: "n6",
      title: "Review Due",
      type: "topic" as const,
      week: 3,
      status: "review_due" as const,
      sources_status: "insufficient" as const,
    },
    { id: "n7", title: "Midterm", type: "milestone" as const, week: 4 },
  ];
  const allStateEdges = [
    { parent_id: "n1", child_id: "n4", kind: "strict" as const },
    { parent_id: "n4", child_id: "n7", kind: "soft" as const },
  ];

  const view = render(
    <GraphCanvas nodes={allStateNodes} edges={allStateEdges} selectedId="n4" />,
  );
  frame();

  const semanticHues = new Set<string>();
  const semanticTokens = [
    GRAPH_FALLBACK.accent,
    GRAPH_FALLBACK.success,
    GRAPH_FALLBACK.warning,
    GRAPH_FALLBACK.danger,
  ];
  for (const color of [...fillColors, ...strokeColors]) {
    if (semanticTokens.includes(color)) semanticHues.add(color);
  }
  expect(semanticHues.size).toBeLessThanOrEqual(3);
  expect(semanticHues).toEqual(
    new Set([GRAPH_FALLBACK.accent, GRAPH_FALLBACK.success, GRAPH_FALLBACK.warning]),
  );

  const legend = view.container.querySelector(".graph-legend")!;
  expect(legend).not.toBeNull();
  for (const label of [
    "Topic",
    "In progress",
    "Mastered",
    "Needs attention",
    "Milestone",
    "Required",
    "Recommended",
  ]) {
    expect(legend.textContent).toContain(label);
  }
});

it("reads centralized radius, stroke, and motion CSS tokens from the container", () => {
  const realGetComputedStyle = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((el: Element) => {
    const base = realGetComputedStyle(el);
    if (!el.classList.contains("graph-canvas-container")) return base;
    return {
      ...base,
      getPropertyValue: (name: string) =>
        ({
          "--graph-node-radius-min": "20px",
          "--graph-node-radius-max": "32px",
          "--graph-edge-width": "2px",
          "--graph-ring-width": "2.2px",
          "--graph-motion-duration": "0ms",
        })[name] ?? base.getPropertyValue(name),
    } as CSSStyleDeclaration;
  });

  const strokeWidths: number[] = [];
  let currentWidth = 1;
  Object.defineProperty(ctx, "lineWidth", {
    get: () => currentWidth,
    set: (w: number) => {
      currentWidth = w;
      strokeWidths.push(w);
    },
  });

  const view = render(
    <GraphCanvas
      nodes={[{ id: "a", title: "A", type: "topic", week: 1, est_minutes: 30 }]}
      edges={[]}
    />,
  );
  frame();

  // Minimum est_minutes (30) draws with --graph-node-radius-min (20px) and --graph-ring-width (2.2px).
  expect(ctx.arc.mock.calls.some((call: number[]) => call[2] === 20)).toBe(true);
  expect(strokeWidths).toContain(2.2);

  // --graph-motion-duration: 0ms snaps wheel zoom in one step without multi-frame easing.
  fireEvent.wheel(view.container.querySelector("canvas")!, {
    deltaY: -100,
    clientX: 100,
    clientY: 100,
  });
  frame();
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(1.1);
  expect(frames.size).toBe(0);
});

it("normalizes tiny trackpad deltas, zero deltas, deltaMode, bursts, reversals, and mid-animation cursor anchoring", () => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)",
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));

  const view = render(<GraphCanvas nodes={nodes} edges={[]} />);
  const canvas = view.container.querySelector("canvas")!;
  frame();
  expect(frames.size).toBe(0);

  // Zero vertical delta is ignored and schedules no animation frame.
  fireEvent.wheel(canvas, { deltaY: 0, deltaX: 40, clientX: 100, clientY: 100 });
  expect(frames.size).toBe(0);
  expect(view.container.querySelector(".graph-zoom-level")?.textContent).toBe("100%");

  // 12 tiny trackpad ticks (-4px each) scale smoothly instead of compounding to 300%.
  for (let i = 0; i < 12; i++) {
    fireEvent.wheel(canvas, { deltaY: -4, deltaMode: 0, clientX: 100, clientY: 100 });
  }
  frame();
  frame();
  const tinyZoom = ctx.scale.mock.lastCall[0];
  expect(tinyZoom).toBeGreaterThan(1.03);
  expect(tinyZoom).toBeLessThan(1.1);

  // Reset back to 100% (zoom=1, pan={60,60}).
  fireEvent.click(screen.getByLabelText("Reset view"));
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(1);

  // deltaMode=1 (line) scales by line height (~16px/line => -3 lines = -48px).
  fireEvent.wheel(canvas, { deltaY: -3, deltaMode: 1, clientX: 100, clientY: 100 });
  frame();
  frame();
  const lineZoom = ctx.scale.mock.lastCall[0];
  expect(lineZoom).toBeCloseTo(Math.exp(48 * (Math.log(1.1) / 100)), 3);

  // deltaMode=2 (page) normalizes relative to viewport height and stays capped per step.
  fireEvent.click(screen.getByLabelText("Reset view"));
  frame();
  fireEvent.wheel(canvas, { deltaY: -1, deltaMode: 2, clientX: 100, clientY: 100 });
  frame();
  frame();
  const pageZoom = ctx.scale.mock.lastCall[0];
  expect(pageZoom).toBeGreaterThan(1.15);
  expect(pageZoom).toBeLessThan(1.3);

  // Unusually large deltas and rapid bursts are bounded below 300%.
  let mockNow = 1000;
  vi.spyOn(performance, "now").mockImplementation(() => mockNow);
  fireEvent.click(screen.getByLabelText("Reset view"));
  frame();
  for (let i = 0; i < 10; i++) {
    fireEvent.wheel(canvas, { deltaY: -5000, deltaMode: 0, clientX: 100, clientY: 100 });
  }
  frame();
  frame();
  const burstZoom = ctx.scale.mock.lastCall[0];
  expect(burstZoom).toBeLessThan(2.0);

  // Immediate direction reversal works without waiting for burst window expiry.
  fireEvent.wheel(canvas, { deltaY: 100, deltaMode: 0, clientX: 100, clientY: 100 });
  frame();
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeLessThan(burstZoom);
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(burstZoom / 1.1, 3);
});

it("keeps world point anchored under moving cursor during in-flight wheel animation", () => {
  const view = render(<GraphCanvas nodes={nodes} edges={[]} />);
  const canvas = view.container.querySelector("canvas")!;
  frame();

  fireEvent.wheel(canvas, { deltaY: -100, clientX: 100, clientY: 100 });
  frame(); // 1st step updates viewGoal interpolation & queues redraw tick
  frame(); // 2nd frame runs redraw tick with the in-flight pan & zoom on ctx
  const midZoom = ctx.scale.mock.lastCall[0];
  const midPanX = ctx.translate.mock.lastCall[0];
  const midPanY = ctx.translate.mock.lastCall[1];
  expect(midZoom).toBeGreaterThan(1);
  const cursorX2 = 220;
  const cursorY2 = 160;
  const expectedWorldX2 = (cursorX2 - midPanX) / midZoom;
  const expectedWorldY2 = (cursorY2 - midPanY) / midZoom;

  fireEvent.wheel(canvas, { deltaY: -100, clientX: cursorX2, clientY: cursorY2 });
  for (let i = 0; i < 80 && frames.size > 0; i++) frame();
  const finalZoom = ctx.scale.mock.lastCall[0];
  const finalPanX = ctx.translate.mock.lastCall[0];
  const finalPanY = ctx.translate.mock.lastCall[1];
  expect(finalZoom).toBeCloseTo(1.21, 2);
  expect(finalPanX).toBeCloseTo(cursorX2 - expectedWorldX2 * finalZoom, 1);
  expect(finalPanY).toBeCloseTo(cursorY2 - expectedWorldY2 * finalZoom, 1);
});

it("anchors off-center touch pinch midpoint, cleans up lost capture/cancel, and never accidentally selects or wires nodes", () => {
  class PolyfillPointerEvent extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  vi.stubGlobal("PointerEvent", PolyfillPointerEvent);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 800,
    height: 600,
    left: 0,
    top: 0,
    right: 800,
    bottom: 600,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);

  const select = vi.fn();
  const createEdge = vi.fn();
  const view = render(
    <GraphCanvas nodes={nodes} edges={[]} onSelect={select} onEdgeCreate={createEdge} />,
  );
  const canvas = view.container.querySelector("canvas")!;
  frame();
  fireEvent.click(screen.getByLabelText("Reset view"));
  frame();

  // Touch on background at (160, 120) and (260, 120): initial midpoint (210, 120), distance 100.
  // At pan=(60,60), zoom=1 => worldMid = (150, 60).
  fireEvent.pointerDown(canvas, { pointerId: 1, pointerType: "touch", clientX: 160, clientY: 120 });
  select.mockClear();
  fireEvent.pointerDown(canvas, { pointerId: 2, pointerType: "touch", clientX: 260, clientY: 120 });

  // Double distance -> zoom=2 AND move midpoint to (310, 220) => pan should move to Keep worldMid=(150,60) at (310,220).
  fireEvent.pointerMove(canvas, { pointerId: 1, pointerType: "touch", clientX: 210, clientY: 220 });
  fireEvent.pointerMove(canvas, { pointerId: 2, pointerType: "touch", clientX: 410, clientY: 220 });
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(2);
  expect(ctx.translate.mock.lastCall[0]).toBeCloseTo(310 - 150 * 2, 1);
  expect(ctx.translate.mock.lastCall[1]).toBeCloseTo(220 - 60 * 2, 1);

  // Release pointer 2 while pointer 1 remains, then lift pointer 1 over node "a" -> no accidental selection or edge creation.
  fireEvent.pointerUp(canvas, { pointerId: 2, pointerType: "touch", clientX: 410, clientY: 220 });
  fireEvent.pointerUp(canvas, { pointerId: 1, pointerType: "touch", clientX: 220, clientY: 220 });
  expect(select).not.toHaveBeenCalled();
  expect(createEdge).not.toHaveBeenCalled();

  // Interrupt a pinch with lostpointercapture & pointercancel, then verify 1-finger drag pans normally.
  fireEvent.pointerDown(canvas, { pointerId: 3, pointerType: "touch", clientX: 100, clientY: 300 });
  fireEvent.pointerDown(canvas, { pointerId: 4, pointerType: "touch", clientX: 200, clientY: 300 });
  fireEvent(canvas, Object.assign(new Event("lostpointercapture", { bubbles: true }), { pointerId: 4 }));
  fireEvent(canvas, Object.assign(new Event("pointercancel", { bubbles: true }), { pointerId: 3 }));

  const panBefore = {
    x: ctx.translate.mock.lastCall[0],
    y: ctx.translate.mock.lastCall[1],
    z: ctx.scale.mock.lastCall[0],
  };
  fireEvent.pointerDown(canvas, { pointerId: 5, pointerType: "touch", clientX: 400, clientY: 400 });
  fireEvent.pointerMove(canvas, { pointerId: 5, pointerType: "touch", clientX: 460, clientY: 430 });
  fireEvent.pointerUp(canvas, { pointerId: 5, pointerType: "touch", clientX: 460, clientY: 430 });
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(panBefore.z);
  expect(ctx.translate.mock.lastCall[0]).toBeCloseTo(panBefore.x + 60, 1);
  expect(ctx.translate.mock.lastCall[1]).toBeCloseTo(panBefore.y + 30, 1);
});

it("fits wide 15-week mobile graphs below 30% without zoom snapping, re-frames disjoint/equal-count roadmaps, and highlights low-zoom focused nodes", () => {
  class PolyfillPointerEvent extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  vi.stubGlobal("PointerEvent", PolyfillPointerEvent);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 360,
    height: 520,
    left: 0,
    top: 0,
    right: 360,
    bottom: 520,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);

  const wideNodes = Array.from({ length: 15 }, (_, i) => ({
    id: `w1-${i + 1}`,
    title: `Week Topic ${i + 1}`,
    type: i === 14 ? ("milestone" as const) : ("topic" as const),
    week: i + 1,
    est_minutes: 60,
  }));

  const view = render(<GraphCanvas graphId="rm-1" nodes={wideNodes} edges={[]} />);
  frame();
  const fitZoom = ctx.scale.mock.lastCall[0];
  const fitPanX = ctx.translate.mock.lastCall[0];
  expect(fitZoom).toBeLessThan(0.2);

  // Every visible glyph fits horizontally inside [0, 360].
  const leftEdge = fitPanX + (80 - 30) * fitZoom;
  const rightEdge = fitPanX + (14 * 180 + 80 + 30) * fitZoom;
  expect(leftEdge).toBeGreaterThanOrEqual(0);
  expect(rightEdge).toBeLessThanOrEqual(360);

  // Next wheel zoom-out and '-' key do NOT snap zoom upward to 0.2.
  fireEvent.wheel(view.container.querySelector("canvas")!, {
    deltaY: 100,
    clientX: 180,
    clientY: 260,
  });
  for (let i = 0; i < 60 && frames.size > 0; i++) frame();
  const afterWheelZoom = ctx.scale.mock.lastCall[0];
  expect(afterWheelZoom).toBeLessThan(0.2);
  expect(afterWheelZoom).toBeLessThanOrEqual(fitZoom);

  fireEvent.keyDown(screen.getByRole("region"), { key: "-" });
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeLessThan(0.2);
  expect(ctx.scale.mock.lastCall[0]).toBeLessThanOrEqual(afterWheelZoom);

  // Subsequent touch pinch out and wheel zoom-out/in also stay below 0.2 without snapping upward.
  fireEvent.pointerDown(view.container.querySelector("canvas")!, {
    pointerId: 11,
    pointerType: "touch",
    clientX: 120,
    clientY: 260,
  });
  fireEvent.pointerDown(view.container.querySelector("canvas")!, {
    pointerId: 12,
    pointerType: "touch",
    clientX: 240,
    clientY: 260,
  });
  fireEvent.pointerMove(view.container.querySelector("canvas")!, {
    pointerId: 11,
    pointerType: "touch",
    clientX: 130,
    clientY: 260,
  });
  fireEvent.pointerUp(view.container.querySelector("canvas")!, {
    pointerId: 12,
    pointerType: "touch",
    clientX: 240,
    clientY: 260,
  });
  fireEvent.pointerUp(view.container.querySelector("canvas")!, {
    pointerId: 11,
    pointerType: "touch",
    clientX: 130,
    clientY: 260,
  });
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeLessThan(0.2);

  // Deliberate user pan on same roadmap survives an ordinary node-status refresh.
  fireEvent.keyDown(screen.getByRole("region"), { key: "ArrowRight" });
  frame();
  const userPanX = ctx.translate.mock.lastCall[0];
  const userZoom = ctx.scale.mock.lastCall[0];
  view.rerender(
    <GraphCanvas
      graphId="rm-1"
      nodes={wideNodes.map((n, i) => (i === 0 ? { ...n, status: "mastered" as const } : n))}
      edges={[]}
    />,
  );
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeCloseTo(userZoom);
  expect(ctx.translate.mock.lastCall[0]).toBeCloseTo(userPanX);

  // Switching to a different roadmap with the exact SAME node count (15) re-frames cleanly (with graphId and disjoint IDs).
  const equalCountAlt = Array.from({ length: 15 }, (_, i) => ({
    id: `rm2-${i + 1}`,
    title: `Alt ${i + 1}`,
    type: "topic" as const,
    week: Math.floor(i / 3) + 1,
    est_minutes: 60,
  }));
  expect(equalCountAlt.length).toBe(wideNodes.length);
  view.rerender(<GraphCanvas graphId="rm-2" nodes={equalCountAlt} edges={[]} />);
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeGreaterThan(0.25);

  const disjointEqualCount = Array.from({ length: 15 }, (_, i) => ({
    id: `rm3-${i + 1}`,
    title: `Third ${i + 1}`,
    type: "topic" as const,
    week: i + 1,
    est_minutes: 60,
  }));
  view.rerender(<GraphCanvas nodes={disjointEqualCount} edges={[]} />);
  frame();
  expect(ctx.scale.mock.lastCall[0]).toBeLessThan(0.2);

  // Selected node at low zoom keeps its focus ring and contrast label pill drawn.
  ctx.fillText.mockClear();
  ctx.fillRect.mockClear();
  view.rerender(
    <GraphCanvas
      graphId="rm-1"
      nodes={wideNodes}
      edges={[]}
      selectedId="w1-8"
    />,
  );
  for (let i = 0; i < 60 && frames.size > 0; i++) frame();
  frame();
  expect(
    ctx.fillText.mock.calls.some((args: unknown[]) => args[0] === "Week Topic 8"),
  ).toBe(true);
});
