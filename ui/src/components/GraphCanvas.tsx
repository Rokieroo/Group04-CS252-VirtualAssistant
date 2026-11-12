import React, { useCallback, useEffect, useRef, useState } from "react";
import "./GraphCanvas.css";

export interface GraphNode {
  id: string;
  title: string;
  type: "topic" | "milestone";
  week?: number | null;
  layer?: number | null;
  est_minutes?: number;
  status?:
    | "not_started"
    | "in_progress"
    | "mastered"
    | "review_due"
    | "locked"
    | "available";
  sources_status?: "sufficient" | "insufficient" | "pending";
  clo?: string[];
  covers?: string[];
  x?: number;
  y?: number;
  pinned?: boolean;
}

export interface GraphEdge {
  parent_id: string;
  child_id: string;
  kind?: "strict" | "soft" | "covers";
  origin?: "week_order" | "llm" | "user" | "milestone_covers";
  confidence?: number;
  reason?: string;
}

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  cycleEdges?: GraphEdge[];
  layout?: "week" | "force";
  selectedId?: string | null;
  highlightedIds?: string[];
  onSelect?: (nodeId: string | null) => void;
  onEdgeCreate?: (
    parentId: string,
    childId: string,
  ) => Promise<boolean | void> | boolean | void;
  onLayoutChange?: (
    positions: Array<{
      node_id: string;
      x: number;
      y: number;
      pinned: boolean;
    }>,
  ) => void;
  onLayoutModeChange?: (mode: "week" | "force") => void;
  cyclePath?: string[] | null;
  className?: string;
}

interface InternalNode extends GraphNode {
  vx: number;
  vy: number;
  radius: number;
  displayX: number;
  displayY: number;
  /** Where the node is easing to after a layout change; unset once it arrives. */
  targetX?: number;
  targetY?: number;
}

/**
 * Checks if adding `parentId -> childId` introduces a cycle.
 * Returns the cycle path (e.g. `['B', 'A', 'B']`) if cycle detected, or `null` if DAG is preserved.
 */
export function findCyclePath(
  edges: Array<{ parent_id: string; child_id: string }>,
  parentId: string,
  childId: string,
): string[] | null {
  if (parentId === childId) {
    return [parentId, parentId];
  }

  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (!adjacency.has(edge.parent_id)) {
      adjacency.set(edge.parent_id, []);
    }
    adjacency.get(edge.parent_id)!.push(edge.child_id);
  }

  // BFS / DFS from childId to see if we can reach parentId
  const queue: Array<{ node: string; path: string[] }> = [
    { node: childId, path: [parentId, childId] },
  ];
  const visited = new Set<string>([childId]);

  while (queue.length > 0) {
    const { node, path } = queue.shift()!;
    if (node === parentId) {
      return path;
    }
    const children = adjacency.get(node) || [];
    for (const child of children) {
      if (child === parentId) {
        return [...path, parentId];
      }
      if (!visited.has(child)) {
        visited.add(child);
        queue.push({ node: child, path: [...path, child] });
      }
    }
  }

  return null;
}

/**
 * Canvas colors come from CSS tokens on the container (GraphCanvas.css), so the graph
 * follows the app theme and accent. Canvas cannot read `var(--x)`, so each token is
 * resolved through a hidden swatch's computed `color`. These are the fallbacks when a
 * token cannot be resolved (tests, very old browsers).
 */
export const GRAPH_FALLBACK = {
  surface: "#ffffff",
  band: "#f4f6fb",
  grid: "#dfe4ee",
  ink: "#182439",
  muted: "#66748a",
  edge: "#8a96ab",
  accent: "#6654d9",
  success: "#13805c",
  warning: "#b7791f",
  danger: "#c0392b",
};
export type GraphPalette = typeof GRAPH_FALLBACK;
const PALETTE_KEYS = Object.keys(GRAPH_FALLBACK) as (keyof GraphPalette)[];

function readPalette(swatches: HTMLElement | null): GraphPalette {
  const palette = { ...GRAPH_FALLBACK };
  if (!swatches || typeof getComputedStyle !== "function") return palette;
  const declared = getComputedStyle(swatches);
  for (const key of PALETTE_KEYS) {
    // An undeclared token would resolve to the inherited text colour; keep the fallback.
    if (!declared.getPropertyValue(`--graph-${key}`).trim()) continue;
    const el = swatches.querySelector<HTMLElement>(`[data-token="${key}"]`);
    const color = el ? toRgb(getComputedStyle(el).color) : "";
    if (color) palette[key] = color;
  }
  return palette;
}

/** Any CSS colour (oklab, color-mix results, …) as `rgb(r, g, b)`, or "" if unknown. */
let probe: CanvasRenderingContext2D | null | undefined;
function toRgb(color: string): string {
  if (!color) return "";
  if (/^rgba?\(/.test(color)) return color;
  if (probe === undefined) {
    try {
      probe = document
        .createElement("canvas")
        .getContext("2d", { willReadFrequently: true });
    } catch {
      probe = null;
    }
  }
  if (!probe || typeof probe.getImageData !== "function") return "";
  try {
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = "#000";
    probe.fillStyle = color;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    return `rgb(${r}, ${g}, ${b})`;
  } catch {
    return "";
  }
}

/** `rgb(1, 2, 3)` / `#abc` with an alpha, for faint versions of a token. */
function withAlpha(color: string, alpha: number): string {
  const rgb = color.match(/rgba?\(([^)]+)\)/);
  if (rgb) {
    const [r, g, b] = rgb[1].split(/[ ,/]+/).filter(Boolean);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const hex = color.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const h =
      hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  return color;
}

const EDGE_LABEL: Record<string, string> = {
  strict: "Bắt buộc học trước",
  soft: "Nên học trước",
  covers: "Thuộc mốc kiểm tra",
};
const COLUMN_WIDTH = 180;
const ROW_HEIGHT = 85;
const FONT_STACK = 'Inter, "Segoe UI", Arial, sans-serif';
const HEADER_FONT = '600 10.5px Inter, "Segoe UI", Arial, sans-serif';
const TAG_FONT = '500 11px Inter, "Segoe UI", Arial, sans-serif';

type Point = { x: number; y: number };
interface Placed {
  displayX: number;
  displayY: number;
  radius: number;
  type: "topic" | "milestone";
}

/** The cubic curve of an edge, trimmed to both node rims along its own tangents. */
function curve(a: Placed, b: Placed) {
  const dx = b.displayX - a.displayX;
  const dy = b.displayY - a.displayY;
  const horizontal = Math.abs(dx) >= Math.abs(dy);
  const pull = (horizontal ? dx : dy) * 0.5;
  const c1: Point = horizontal
    ? { x: a.displayX + pull, y: a.displayY }
    : { x: a.displayX, y: a.displayY + pull };
  const c2: Point = horizontal
    ? { x: b.displayX - pull, y: b.displayY }
    : { x: b.displayX, y: b.displayY - pull };
  const straight = Math.atan2(dy, dx);
  const startAngle =
    c1.x === a.displayX && c1.y === a.displayY
      ? straight
      : Math.atan2(c1.y - a.displayY, c1.x - a.displayX);
  const endAngle =
    c2.x === b.displayX && c2.y === b.displayY
      ? straight
      : Math.atan2(b.displayY - c2.y, b.displayX - c2.x);
  const rimB = b.type === "milestone" ? b.radius * 1.15 : b.radius;
  return {
    start: {
      x: a.displayX + Math.cos(startAngle) * (a.radius + 2),
      y: a.displayY + Math.sin(startAngle) * (a.radius + 2),
    },
    c1,
    c2,
    end: {
      x: b.displayX - Math.cos(endAngle) * (rimB + 3),
      y: b.displayY - Math.sin(endAngle) * (rimB + 3),
    },
    endAngle,
  };
}

function pointOn(g: ReturnType<typeof curve>, t: number): Point {
  const mt = 1 - t;
  const k = [mt ** 3, 3 * mt ** 2 * t, 3 * mt * t ** 2, t ** 3];
  return {
    x: k[0] * g.start.x + k[1] * g.c1.x + k[2] * g.c2.x + k[3] * g.end.x,
    y: k[0] * g.start.y + k[1] * g.c1.y + k[2] * g.c2.y + k[3] * g.end.y,
  };
}

export function GraphCanvas({
  nodes,
  edges,
  cycleEdges,
  layout = "week",
  selectedId = null,
  highlightedIds = [],
  onSelect,
  onEdgeCreate,
  onLayoutChange,
  onLayoutModeChange,
  cyclePath = null,
  className = "",
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Transform states
  const [pan, setPan] = useState({ x: 60, y: 60 });
  const [zoom, setZoom] = useState(1);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);
  const [activeCycle, setActiveCycle] = useState<string[] | null>(cyclePath);
  const [cycleAlert, setCycleAlert] = useState<string | null>(null);

  // Interaction dragging states
  const isDraggingNode = useRef(false);
  const draggedNodeId = useRef<string | null>(null);
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const isEdgeDragging = useRef(false);
  const edgeDragSource = useRef<string | null>(null);
  const edgeDragPos = useRef<{ x: number; y: number } | null>(null);
  const layoutDebounceTimer = useRef<number | null>(null);

  // Computed internal node positions
  const internalNodesRef = useRef<Map<string, InternalNode>>(new Map());
  // Set on every render and pointer move; the frame loop draws only when this is set
  // or something is still moving, so an idle graph costs no canvas work.
  const needsDraw = useRef(true);
  needsDraw.current = true;
  const reducedMotion = useRef(
    typeof matchMedia === "function" &&
      matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  // Theme colours, re-read when the app theme, accent or OS scheme changes.
  const swatchesRef = useRef<HTMLDivElement | null>(null);
  const palette = useRef<GraphPalette>(GRAPH_FALLBACK);
  useEffect(() => {
    const refresh = () => {
      palette.current = readPalette(swatchesRef.current);
      needsDraw.current = true;
    };
    refresh();
    const observer =
      typeof MutationObserver !== "undefined"
        ? new MutationObserver(refresh)
        : null;
    observer?.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-accent", "class", "style"],
    });
    const scheme =
      typeof matchMedia === "function"
        ? matchMedia("(prefers-color-scheme: dark)")
        : null;
    scheme?.addEventListener?.("change", refresh);
    return () => {
      observer?.disconnect();
      scheme?.removeEventListener?.("change", refresh);
    };
  }, []);

  // Update activeCycle and cycleAlert when prop changes
  useEffect(() => {
    setActiveCycle(cyclePath);
    if (cyclePath && cyclePath.length > 1) {
      setCycleAlert(`Chu trình tiên quyết bị chặn: ${cyclePath.join(" → ")}`);
    } else {
      setCycleAlert(null);
    }
  }, [cyclePath]);

  // Compute node size based on est_minutes
  const getNodeRadius = useCallback((node: GraphNode): number => {
    const mins = node.est_minutes ?? 60;
    const clamped = Math.max(30, Math.min(mins, 240));
    return 16 + ((clamped - 30) / 210) * 12; // 16px to 28px
  }, []);

  const previousLayout = useRef(layout);
  const drawRef = useRef<() => void>(() => {});
  const persistRef = useRef(onLayoutChange);
  persistRef.current = onLayoutChange;

  // Initialize and place nodes
  useEffect(() => {
    const changedLayout = previousLayout.current !== layout;
    previousLayout.current = layout;
    const map = internalNodesRef.current;
    const newMap = new Map<string, InternalNode>();

    // Week column placement
    const colWidth = COLUMN_WIDTH;
    const rowHeight = ROW_HEIGHT;

    // Group nodes by week
    const weekGroups = new Map<number, GraphNode[]>();
    for (const node of nodes) {
      const w = node.week ?? node.layer ?? 1;
      if (!weekGroups.has(w)) weekGroups.set(w, []);
      weekGroups.get(w)!.push(node);
    }
    const tallestWeek = Math.max(
      1,
      ...[...weekGroups.values()].map((g) => g.length),
    );

    nodes.forEach((node) => {
      const prev = map.get(node.id);
      const radius = getNodeRadius(node);
      const pinned = prev?.pinned ?? node.pinned ?? false;
      let initX =
        node.pinned && node.x !== undefined
          ? node.x
          : changedLayout && !pinned
            ? undefined
            : (prev?.displayX ?? node.x);
      let initY =
        node.pinned && node.y !== undefined
          ? node.y
          : changedLayout && !pinned
            ? undefined
            : (prev?.displayY ?? node.y);

      if (initX === undefined || initY === undefined) {
        if (layout === "week") {
          const w = node.week ?? node.layer ?? 1;
          const list = weekGroups.get(w) || [node];
          const indexInWeek = list.findIndex((n) => n.id === node.id);
          // Short weeks sit centred against the busiest one instead of hugging the top.
          const offset = ((tallestWeek - list.length) * rowHeight) / 2;
          initX = (w - 1) * colWidth + 80;
          initY = offset + indexInWeek * rowHeight + 80;
        } else if (prev) {
          // The simulation settles from where the nodes are now, not a fresh scatter.
          initX = prev.displayX;
          initY = prev.displayY;
        } else {
          // Golden-angle spiral: the same graph always settles the same way.
          const i = nodes.indexOf(node);
          const angle = i * 2.39996;
          const r = 60 + 26 * Math.sqrt(i + 1);
          initX = 450 + Math.cos(angle) * r;
          initY = 320 + Math.sin(angle) * r;
        }
      }

      // A node already on screen glides to its week column instead of jumping.
      const glide = changedLayout && prev && !pinned && layout === "week";
      newMap.set(node.id, {
        ...node,
        vx: 0,
        vy: 0,
        radius,
        displayX: glide ? prev.displayX : initX,
        displayY: glide ? prev.displayY : initY,
        targetX: glide ? initX : layout === "week" ? prev?.targetX : undefined,
        targetY: glide ? initY : layout === "week" ? prev?.targetY : undefined,
        pinned: prev?.pinned ?? node.pinned ?? false,
      });
    });

    internalNodesRef.current = newMap;
  }, [nodes, layout, getNodeRadius]);

  // Force simulation animation loop
  useEffect(() => {
    let animId: number;

    const tick = () => {
      const nodeMap = internalNodesRef.current;
      const nodeList = Array.from(nodeMap.values());
      let moving = false;

      // Keep the graph steady while the user manipulates the viewport.
      if (layout === "force" && nodeList.length > 0 && !isPanning.current) {
        // 1. Repulsion between all nodes
        for (let i = 0; i < nodeList.length; i++) {
          for (let j = i + 1; j < nodeList.length; j++) {
            const a = nodeList[i];
            const b = nodeList[j];
            const dx = b.displayX - a.displayX;
            const dy = b.displayY - a.displayY;
            const distanceSquared = dx * dx + dy * dy;
            if (distanceSquared < 350 * 350) {
              const dist = Math.sqrt(distanceSquared) || 1;
              const force = (800 / (dist * dist)) * 0.8;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;
              if (!a.pinned) {
                a.vx -= fx;
                a.vy -= fy;
              }
              if (!b.pinned) {
                b.vx += fx;
                b.vy += fy;
              }
            }
          }
        }

        // 2. Spring attraction along edges
        edges.forEach((edge) => {
          const p = nodeMap.get(edge.parent_id);
          const c = nodeMap.get(edge.child_id);
          if (p && c) {
            const dx = c.displayX - p.displayX;
            const dy = c.displayY - p.displayY;
            const dist = Math.hypot(dx, dy) || 1;
            const targetDist = 120;
            const force = (dist - targetDist) * 0.04;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            if (!p.pinned) {
              p.vx += fx;
              p.vy += fy;
            }
            if (!c.pinned) {
              c.vx -= fx;
              c.vy -= fy;
            }
          }
        });

        // 3. Center gravity pull
        const cx = 450;
        const cy = 320;
        nodeList.forEach((n) => {
          if (!n.pinned) {
            n.vx += (cx - n.displayX) * 0.005;
            n.vy += (cy - n.displayY) * 0.005;

            // Apply friction & update
            n.vx *= 0.85;
            n.vy *= 0.85;
            n.displayX += n.vx;
            n.displayY += n.vy;
            if (Math.abs(n.vx) + Math.abs(n.vy) > 0.02) moving = true;
          }
        });
      }

      const ease = reducedMotion.current ? 1 : 0.18;
      for (const n of nodeList) {
        if (n.targetX === undefined || n.targetY === undefined) continue;
        n.displayX += (n.targetX - n.displayX) * ease;
        n.displayY += (n.targetY - n.displayY) * ease;
        if (Math.hypot(n.targetX - n.displayX, n.targetY - n.displayY) < 0.5) {
          n.displayX = n.targetX;
          n.displayY = n.targetY;
          n.targetX = n.targetY = undefined;
        }
        moving = true;
      }

      if (moving || needsDraw.current) {
        needsDraw.current = false;
        drawRef.current();
      }
      animId = requestAnimationFrame(tick);
    };

    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [layout, edges]);

  // Main Canvas Render
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const c = palette.current;

    const width = canvas.width;
    const height = canvas.height;
    const dpr =
      typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    const viewW = width / dpr;
    const viewH = height / dpr;
    ctx.clearRect(0, 0, width, height);

    const nodeMap = internalNodesRef.current;
    const activeHover = highlightedIds.length
      ? null
      : hoveredNodeId || selectedId;

    // Neighbours of the focused node stay bright; everything else steps back.
    const neighborSet = new Set<string>(highlightedIds);
    if (activeHover) {
      neighborSet.add(activeHover);
      edges.forEach((edge) => {
        if (edge.parent_id === activeHover) neighborSet.add(edge.child_id);
        if (edge.child_id === activeHover) neighborSet.add(edge.parent_id);
      });
    }
    const focusing = Boolean(activeHover) || highlightedIds.length > 0;

    const cycleEdgeSet = new Set<string>();
    if (activeCycle && activeCycle.length > 1) {
      for (let i = 0; i < activeCycle.length - 1; i++) {
        cycleEdgeSet.add(`${activeCycle[i]}>${activeCycle[i + 1]}`);
      }
    }

    // World-space bounds of the visible area, for the background.
    const left = -pan.x / zoom;
    const top = -pan.y / zoom;
    const right = left + viewW / zoom;
    const bottom = top + viewH / zoom;

    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(zoom, zoom);

    // 1. Background: alternate week bands, then a quiet dot grid.
    const maxWeek = Math.max(
      ...Array.from(nodeMap.values()).map((n) => n.week ?? n.layer ?? 1),
      1,
    );
    if (layout === "week") {
      ctx.fillStyle = c.band;
      for (let w = 2; w <= maxWeek; w += 2) {
        ctx.fillRect(
          (w - 1) * COLUMN_WIDTH - 10,
          top,
          COLUMN_WIDTH,
          bottom - top,
        );
      }
    }
    if (zoom >= 0.45) {
      const step = 24;
      ctx.fillStyle = c.grid;
      const dot = 1.1 / zoom;
      for (let gx = Math.floor(left / step) * step; gx <= right; gx += step) {
        for (let gy = Math.floor(top / step) * step; gy <= bottom; gy += step) {
          ctx.fillRect(gx - dot / 2, gy - dot / 2, dot, dot);
        }
      }
    }

    // 2. Edges: thin curves in one neutral; the focused path takes the accent.
    const drawEdge = (edge: GraphEdge, strong: boolean) => {
      const parent = nodeMap.get(edge.parent_id);
      const child = nodeMap.get(edge.child_id);
      if (!parent || !child) return;
      const isCycleEdge = cycleEdgeSet.has(
        `${edge.parent_id}>${edge.child_id}`,
      );
      const inFocus =
        neighborSet.has(edge.parent_id) && neighborSet.has(edge.child_id);
      if (strong !== (isCycleEdge || (focusing && inFocus))) return;

      const kind = edge.kind ?? "strict";
      let color: string;
      if (isCycleEdge) color = c.danger;
      else if (focusing && inFocus) color = c.accent;
      // Week-order and milestone edges are numerous; they stay a whisper until focused.
      else
        color = withAlpha(
          c.edge,
          (focusing ? 0.35 : 1) *
            (kind === "covers" ? 0.16 : kind === "soft" ? 0.3 : 0.75),
        );

      const g = curve(parent, child);
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth =
        (isCycleEdge ? 2.5 : strong ? 1.8 : 1.2) / Math.sqrt(zoom);
      ctx.lineCap = "round";
      ctx.setLineDash(
        isCycleEdge
          ? []
          : kind === "soft"
            ? [4, 4]
            : kind === "covers"
              ? [1, 4]
              : [],
      );
      ctx.beginPath();
      ctx.moveTo(g.start.x, g.start.y);
      ctx.bezierCurveTo(g.c1.x, g.c1.y, g.c2.x, g.c2.y, g.end.x, g.end.y);
      ctx.stroke();

      // A small closed arrowhead along the tangent at the child end.
      if (kind !== "covers" || strong) {
        const size = (isCycleEdge || strong ? 7 : 5.5) / Math.sqrt(zoom);
        ctx.setLineDash([]);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(g.end.x, g.end.y);
        ctx.lineTo(
          g.end.x - size * Math.cos(g.endAngle - 0.42),
          g.end.y - size * Math.sin(g.endAngle - 0.42),
        );
        ctx.lineTo(
          g.end.x - size * Math.cos(g.endAngle + 0.42),
          g.end.y - size * Math.sin(g.endAngle + 0.42),
        );
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    };
    // Faint edges first, so the focused path is never painted over.
    edges.forEach((edge) => drawEdge(edge, false));
    edges.forEach((edge) => drawEdge(edge, true));

    // 3. Rubber band while Shift-dragging a new prerequisite.
    if (
      isEdgeDragging.current &&
      edgeDragSource.current &&
      edgeDragPos.current
    ) {
      const src = nodeMap.get(edgeDragSource.current);
      if (src) {
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = c.accent;
        ctx.lineWidth = 1.8 / Math.sqrt(zoom);
        ctx.setLineDash([5, 4]);
        ctx.moveTo(src.displayX, src.displayY);
        ctx.lineTo(edgeDragPos.current.x, edgeDragPos.current.y);
        ctx.stroke();
        ctx.restore();
      }
    }

    // 4. Nodes. Status reads from fill and ring, not from a rainbow of hues.
    const labels: Array<{
      node: InternalNode;
      important: boolean;
      dim: boolean;
    }> = [];
    nodeMap.forEach((node) => {
      const isSelected = selectedId === node.id;
      const isHovered = hoveredNodeId === node.id;
      const isCycle = activeCycle?.includes(node.id) ?? false;
      const isNeighbor = !focusing || neighborSet.has(node.id);
      const status = node.status || "not_started";
      const x = node.displayX;
      const y = node.displayY;
      const r = node.radius;

      ctx.save();
      ctx.globalAlpha = isNeighbor ? 1 : 0.28;

      const shape = (radius: number) => {
        ctx.beginPath();
        if (node.type === "milestone") {
          const d = radius * 1.15;
          ctx.moveTo(x, y - d);
          ctx.lineTo(x + d, y);
          ctx.lineTo(x, y + d);
          ctx.lineTo(x - d, y);
          ctx.closePath();
        } else {
          ctx.arc(x, y, radius, 0, Math.PI * 2);
        }
      };

      // Selection halo: one soft disc of the accent behind the node.
      if (isSelected || isHovered) {
        shape(r + (isSelected ? 7 : 5));
        ctx.fillStyle = withAlpha(
          isCycle ? c.danger : c.accent,
          isSelected ? 0.16 : 0.1,
        );
        ctx.fill();
      }

      let fill = c.surface;
      let ring = withAlpha(c.edge, 0.9);
      let ringWidth = 1.5;
      let dash: number[] = [];
      if (node.type === "milestone") {
        fill = c.ink;
        ring = c.ink;
      } else if (status === "mastered") {
        fill = c.success;
        ring = c.success;
      } else if (status === "in_progress") {
        ring = c.accent;
        ringWidth = 2.5;
      } else if (status === "available") {
        ring = c.accent;
      } else if (status === "review_due") {
        ring = c.warning;
        ringWidth = 2.5;
      } else if (status === "locked") {
        dash = [3, 3];
      }
      if (isCycle) {
        fill = c.danger;
        ring = c.danger;
      }
      if (isSelected) {
        ring = isCycle ? c.danger : c.accent;
        ringWidth = 3;
      }

      shape(r);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.setLineDash(dash);
      ctx.strokeStyle = ring;
      ctx.lineWidth = ringWidth;
      ctx.stroke();
      ctx.setLineDash([]);

      // In progress: a short inner arc, so it reads at a glance even without colour.
      if (status === "in_progress" && node.type !== "milestone" && !isCycle) {
        ctx.beginPath();
        ctx.arc(x, y, r * 0.45, -Math.PI / 2, Math.PI / 2);
        ctx.strokeStyle = c.accent;
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Not enough sources: a small warning notch on the rim.
      if (node.sources_status === "insufficient") {
        const nx = x + r * 0.72;
        const ny = y - r * 0.72;
        ctx.beginPath();
        ctx.arc(nx, ny, 4, 0, Math.PI * 2);
        ctx.fillStyle = c.warning;
        ctx.fill();
        ctx.strokeStyle = c.surface;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      ctx.restore();

      labels.push({
        node,
        important:
          isSelected ||
          isHovered ||
          node.type === "milestone" ||
          (focusing && isNeighbor),
        dim: !isNeighbor,
      });
    });

    // 5. Labels keep a constant on-screen size; important ones claim space first,
    // the rest appear only where they fit, so zooming in reveals more of them.
    const placed: Array<{ x0: number; y0: number; x1: number; y1: number }> =
      [];
    const px = 1 / zoom;
    const rank = (l: (typeof labels)[number]) =>
      l.node.id === selectedId
        ? 3
        : l.node.id === hoveredNodeId
          ? 2
          : Number(l.important);
    labels
      .sort((a, b) => rank(b) - rank(a))
      .forEach(({ node, important, dim }) => {
        if (!important && (dim || zoom < 0.35)) return;
        const isSelected = selectedId === node.id || hoveredNodeId === node.id;
        const strong = isSelected || node.type === "milestone";
        const text =
          node.title.length > 26
            ? node.title.slice(0, 24).trimEnd() + "…"
            : node.title;
        ctx.font = `${strong ? 600 : 500} ${12 * px}px ${FONT_STACK}`;
        const w =
          typeof ctx.measureText === "function"
            ? ctx.measureText(text).width
            : text.length * 6.5 * px;
        const rim =
          node.type === "milestone" ? node.radius * 1.15 : node.radius;
        const ly = node.displayY + rim + 15 * px;
        const box = {
          x0: node.displayX - w / 2 - 4 * px,
          y0: ly - 11 * px,
          x1: node.displayX + w / 2 + 4 * px,
          y1: ly + 4 * px,
        };
        const clash = placed.some(
          (p) =>
            box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0,
        );
        if (clash && !isSelected) return;
        placed.push(box);
        ctx.save();
        ctx.globalAlpha = dim ? 0.4 : 1;
        ctx.textAlign = "center";
        ctx.lineJoin = "round";
        if (typeof ctx.strokeText === "function") {
          // A halo in the canvas colour keeps text readable across edges.
          ctx.strokeStyle = c.surface;
          ctx.lineWidth = 4 * px;
          ctx.strokeText(text, node.displayX, ly);
        }
        ctx.fillStyle = strong ? c.ink : withAlpha(c.ink, 0.8);
        ctx.fillText(text, node.displayX, ly);
        ctx.restore();
      });

    // 6. Hovered edge: a small tag in plain words at the curve's midpoint.
    if (hoveredEdge) {
      const a = nodeMap.get(hoveredEdge.parent_id);
      const b = nodeMap.get(hoveredEdge.child_id);
      if (a && b) {
        const g = curve(a, b);
        const { x: mx, y: my } = pointOn(g, 0.5);
        const kind = hoveredEdge.kind ?? "strict";
        const label = `${EDGE_LABEL[kind] ?? kind} · ${Math.round(
          (hoveredEdge.confidence ?? 1) * 100,
        )}%`;
        ctx.save();
        ctx.translate(mx, my);
        ctx.scale(1 / zoom, 1 / zoom);
        ctx.font = TAG_FONT;
        const w =
          typeof ctx.measureText === "function"
            ? ctx.measureText(label).width
            : label.length * 6;
        ctx.fillStyle = c.ink;
        ctx.fillRect(-w / 2 - 8, -12, w + 16, 22);
        ctx.fillStyle = c.surface;
        ctx.textAlign = "center";
        ctx.fillText(label, 0, 3.5);
        ctx.restore();
      }
    }

    ctx.restore();

    // 7. Week headers stay pinned to the top edge while the graph pans underneath.
    if (layout === "week") {
      ctx.save();
      ctx.fillStyle = withAlpha(c.surface, 0.92);
      ctx.fillRect(0, 0, viewW, 26);
      ctx.fillStyle = withAlpha(c.edge, 0.35);
      ctx.fillRect(0, 26, viewW, 1);
      ctx.font = HEADER_FONT;
      ctx.textAlign = "center";
      ctx.fillStyle = c.muted;
      for (let w = 1; w <= maxWeek; w++) {
        const sx = pan.x + ((w - 1) * COLUMN_WIDTH + 80) * zoom;
        if (sx < -40 || sx > viewW + 40) continue;
        ctx.fillText(`TUẦN ${w}`, sx, 17);
      }
      ctx.restore();
    }
  }, [
    pan,
    zoom,
    edges,
    hoveredNodeId,
    highlightedIds,
    hoveredEdge,
    selectedId,
    activeCycle,
    layout,
  ]);

  drawRef.current = draw;

  useEffect(
    () => () => {
      if (layoutDebounceTimer.current)
        window.clearTimeout(layoutDebounceTimer.current);
    },
    [],
  );

  // Coordinate conversion helpers
  const screenToCanvas = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      const x = (clientX - rect.left - pan.x) / zoom;
      const y = (clientY - rect.top - pan.y) / zoom;
      return { x, y };
    },
    [pan, zoom],
  );

  const findNodeAt = useCallback(
    (x: number, y: number): InternalNode | null => {
      const nodeMap = internalNodesRef.current;
      for (const node of nodeMap.values()) {
        const dist = Math.hypot(node.displayX - x, node.displayY - y);
        if (dist <= node.radius + 4) {
          return node;
        }
      }
      return null;
    },
    [],
  );

  // Wheel zoom and focusing a node glide to their goal; buttons and keys stay one step.
  type View = { pan: { x: number; y: number }; zoom: number };
  const view = useRef<View>({ pan, zoom });
  view.current = { pan, zoom };
  const viewGoal = useRef<View | null>(null);
  const viewFrame = useRef(0);
  useEffect(() => () => cancelAnimationFrame(viewFrame.current), []);
  const animateView = (goal: View) => {
    viewGoal.current = goal;
    if (viewFrame.current) return;
    const step = () => {
      const target = viewGoal.current;
      if (!target) {
        viewFrame.current = 0;
        return;
      }
      const k = reducedMotion.current ? 1 : 0.25;
      const { pan: p, zoom: z } = view.current;
      const next = {
        zoom: z + (target.zoom - z) * k,
        pan: {
          x: p.x + (target.pan.x - p.x) * k,
          y: p.y + (target.pan.y - p.y) * k,
        },
      };
      const done =
        Math.abs(target.zoom - next.zoom) < 0.002 &&
        Math.hypot(target.pan.x - next.pan.x, target.pan.y - next.pan.y) < 0.5;
      // Continue from this frame even before React re-renders with it.
      view.current = done ? target : next;
      setZoom(view.current.zoom);
      setPan(view.current.pan);
      if (done) viewGoal.current = null;
      viewFrame.current = done ? 0 : requestAnimationFrame(step);
    };
    viewFrame.current = requestAnimationFrame(step);
  };

  const dragMoved = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const focusNode = (id: string) => {
    const node = internalNodesRef.current.get(id),
      canvas = canvasRef.current;
    if (node && canvas) {
      const rect = canvas.getBoundingClientRect();
      const goalZoom = (viewGoal.current ?? view.current).zoom;
      animateView({
        zoom: goalZoom,
        pan: {
          x: rect.width / 2 - node.displayX * goalZoom,
          y: rect.height / 2 - node.displayY * goalZoom,
        },
      });
    }
  };
  useEffect(() => {
    if (selectedId) focusNode(selectedId);
  }, [selectedId]);

  /** Frame every node with a margin; needs a measured canvas, so it skips in tests. */
  const fitView = (animate = true) => {
    const canvas = canvasRef.current;
    const list = [...internalNodesRef.current.values()];
    if (!canvas || !list.length) return false;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    const xs = list.map((n) => n.targetX ?? n.displayX);
    const ys = list.map((n) => n.targetY ?? n.displayY);
    // Screen margins: room for labels at the sides, header and toolbar above,
    // legend below.
    const side = 90,
      above = 96,
      below = 64;
    const x0 = Math.min(...xs) - 30,
      x1 = Math.max(...xs) + 30;
    const y0 = Math.min(...ys) - 30,
      y1 = Math.max(...ys) + 40;
    const goalZoom = Math.max(
      0.3,
      Math.min(
        1.4,
        Math.max(1, rect.width - 2 * side) / (x1 - x0),
        Math.max(1, rect.height - above - below) / (y1 - y0),
      ),
    );
    const goal = {
      zoom: goalZoom,
      pan: {
        x: rect.width / 2 - ((x0 + x1) / 2) * goalZoom,
        y:
          above +
          (rect.height - above - below) / 2 -
          ((y0 + y1) / 2) * goalZoom,
      },
    };
    if (animate) animateView(goal);
    else {
      view.current = goal;
      setZoom(goal.zoom);
      setPan(goal.pan);
    }
    return true;
  };
  // First time the graph has nodes and a size: frame it instead of showing a corner.
  const framed = useRef(false);
  useEffect(() => {
    if (!framed.current && nodes.length && !selectedId)
      framed.current = fitView(false);
  }, [nodes.length]);

  // Mouse & Touch Interaction Handlers
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ distance: number; zoom: number } | null>(null);
  const handleMouseDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    viewGoal.current = null;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinch.current = { distance: Math.hypot(b.x - a.x, b.y - a.y), zoom };
      isDraggingNode.current = false;
      isPanning.current = false;
      return;
    }
    const { x, y } = screenToCanvas(e.clientX, e.clientY);
    const clickedNode = findNodeAt(x, y);

    if (e.shiftKey && clickedNode) {
      // Start Shift+drag edge creation
      isEdgeDragging.current = true;
      edgeDragSource.current = clickedNode.id;
      edgeDragPos.current = { x, y };
      setActiveCycle(null);
      setCycleAlert(null);
      return;
    }

    if (clickedNode) {
      // Start node dragging
      isDraggingNode.current = true;
      draggedNodeId.current = clickedNode.id;
      dragMoved.current = false;
      dragStart.current = { x: e.clientX, y: e.clientY };
    } else {
      // Background pan
      isPanning.current = true;
      panStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
      onSelect?.(null);
    }
  };

  const handleMouseMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    needsDraw.current = true;
    if (pointers.current.has(e.pointerId))
      pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch.current && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()];
      setZoom(
        Math.max(
          0.2,
          Math.min(
            3,
            (pinch.current.zoom * Math.hypot(b.x - a.x, b.y - a.y)) /
              Math.max(1, pinch.current.distance),
          ),
        ),
      );
      return;
    }
    const { x, y } = screenToCanvas(e.clientX, e.clientY);

    if (isEdgeDragging.current) {
      edgeDragPos.current = { x, y };
      return;
    }

    if (isDraggingNode.current && draggedNodeId.current) {
      const node = internalNodesRef.current.get(draggedNodeId.current);
      if (node) {
        if (
          Math.hypot(
            e.clientX - dragStart.current.x,
            e.clientY - dragStart.current.y,
          ) < 3 &&
          !dragMoved.current
        )
          return;
        dragMoved.current = true;
        node.displayX = x;
        node.displayY = y;
        node.pinned = true;

        // Debounce onLayoutChange callback
        if (layoutDebounceTimer.current) {
          window.clearTimeout(layoutDebounceTimer.current);
        }
        layoutDebounceTimer.current = window.setTimeout(() => {
          const positions = Array.from(internalNodesRef.current.values()).map(
            (n) => ({
              node_id: n.id,
              x: Math.round(n.displayX),
              y: Math.round(n.displayY),
              pinned: n.pinned ?? false,
            }),
          );
          persistRef.current?.(positions);
        }, 1000);
      }
      return;
    }

    if (isPanning.current) {
      setPan({
        x: e.clientX - panStart.current.x,
        y: e.clientY - panStart.current.y,
      });
      return;
    }

    // Check hover
    const hoverNode = findNodeAt(x, y);
    setHoveredNodeId(hoverNode ? hoverNode.id : null);
    setHoveredEdge(
      hoverNode
        ? null
        : edges.find((edge) => {
            const a = internalNodesRef.current.get(edge.parent_id),
              b = internalNodesRef.current.get(edge.child_id);
            if (!a || !b) return false;
            const g = curve(a, b);
            for (let i = 0; i <= 16; i++) {
              const pt = pointOn(g, i / 16);
              if (Math.hypot(x - pt.x, y - pt.y) < 7 / zoom) return true;
            }
            return false;
          }) || null,
    );
  };

  const handleMouseUp = async (e: React.PointerEvent<HTMLCanvasElement>) => {
    pointers.current.delete(e.pointerId);
    if (pinch.current) {
      pinch.current = null;
      pointers.current.clear();
      return;
    }
    if (isEdgeDragging.current && edgeDragSource.current) {
      const { x, y } = screenToCanvas(e.clientX, e.clientY);
      const targetNode = findNodeAt(x, y);

      if (targetNode && targetNode.id !== edgeDragSource.current) {
        const parentId = edgeDragSource.current;
        const childId = targetNode.id;

        // Client-side cycle detection
        const detectedCycle = findCyclePath(
          cycleEdges || edges,
          parentId,
          childId,
        );
        if (detectedCycle) {
          setActiveCycle(detectedCycle);
          setCycleAlert(
            `Chu trình tiên quyết bị chặn: ${detectedCycle.join(" → ")}`,
          );
        } else {
          setActiveCycle(null);
          setCycleAlert(null);
          try {
            await onEdgeCreate?.(parentId, childId);
          } catch (err: unknown) {
            // If API returned 409 conflict, highlight cycle
            const errorObj = err as { detail?: { path?: string[] } };
            if (errorObj?.detail?.path) {
              setActiveCycle(errorObj.detail.path);
              setCycleAlert(
                `API từ chối: chu trình ${errorObj.detail.path.join(" → ")}`,
              );
            } else {
              setCycleAlert(
                err instanceof Error
                  ? err.message
                  : "Could not save prerequisite. Try again.",
              );
            }
          }
        }
      }

      isEdgeDragging.current = false;
      edgeDragSource.current = null;
      edgeDragPos.current = null;
    }

    if (isDraggingNode.current) {
      if (!dragMoved.current && draggedNodeId.current)
        onSelect?.(draggedNodeId.current);
      isDraggingNode.current = false;
      draggedNodeId.current = null;
    }

    if (isPanning.current) {
      isPanning.current = false;
    }
  };

  // Zoom with Wheel
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const ax = e.clientX - rect.left,
      ay = e.clientY - rect.top;
    // Successive wheel ticks build on the goal, so fast scrolling still lands exactly.
    const from = viewGoal.current ?? view.current;
    const goalZoom = Math.max(
      0.2,
      Math.min(3.0, from.zoom * (e.deltaY < 0 ? 1.1 : 0.9)),
    );
    const wx = (ax - from.pan.x) / from.zoom,
      wy = (ay - from.pan.y) / from.zoom;
    animateView({
      zoom: goalZoom,
      pan: { x: ax - wx * goalZoom, y: ay - wy * goalZoom },
    });
  };

  // Keyboard navigation (+ - arrow keys 0)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key))
      e.preventDefault();
    if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      setZoom((z) => Math.min(3.0, z * 1.15));
    } else if (e.key === "-") {
      e.preventDefault();
      setZoom((z) => Math.max(0.2, z * 0.85));
    } else if (e.key === "0") {
      e.preventDefault();
      setZoom(1);
      setPan({ x: 60, y: 60 });
    } else if (e.key === "ArrowLeft") {
      setPan((p) => ({ ...p, x: p.x + 40 }));
    } else if (e.key === "ArrowRight") {
      setPan((p) => ({ ...p, x: p.x - 40 }));
    } else if (e.key === "ArrowUp") {
      setPan((p) => ({ ...p, y: p.y + 40 }));
    } else if (e.key === "ArrowDown") {
      setPan((p) => ({ ...p, y: p.y - 40 }));
    }
  };

  // Resize canvas to parent container
  useEffect(() => {
    const handleResize = () => {
      const container = containerRef.current;
      const canvas = canvasRef.current;
      if (container && canvas) {
        const dpr = window.devicePixelRatio || 1;
        const rect = container.getBoundingClientRect();
        canvas.width = (rect.width || 800) * dpr;
        canvas.height = (rect.height || 550) * dpr;
        const ctx = canvas.getContext("2d");
        ctx?.scale(dpr, dpr);
        needsDraw.current = true;
      }
    };
    handleResize();
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(handleResize)
        : null;
    if (containerRef.current) observer?.observe(containerRef.current);
    window.addEventListener("resize", handleResize);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={`graph-canvas-container ${className}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      role="region"
      aria-label="Knowledge Graph Canvas"
    >
      {/* Hidden swatches: the canvas reads theme colours from these. */}
      <div ref={swatchesRef} className="graph-swatches" aria-hidden="true">
        {PALETTE_KEYS.map((key) => (
          <span key={key} data-token={key} />
        ))}
      </div>

      <div className="graph-toolbar">
        <div className="graph-segmented" role="group" aria-label="Cách sắp xếp">
          <button
            type="button"
            className={layout === "week" ? "active" : ""}
            aria-pressed={layout === "week"}
            onClick={() => onLayoutModeChange?.("week")}
            title="Sắp xếp theo tuần syllabus"
          >
            Theo tuần
          </button>
          <button
            type="button"
            className={layout === "force" ? "active" : ""}
            aria-pressed={layout === "force"}
            onClick={() => onLayoutModeChange?.("force")}
            title="Sắp xếp lực đồ thị kiểu Obsidian"
          >
            Lực (Obsidian)
          </button>
        </div>

        <div className="graph-zoom" role="group" aria-label="Thu phóng">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.2, z * 0.8))}
            title="Thu nhỏ (-)"
            aria-label="Thu nhỏ"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 8h9" />
            </svg>
          </button>
          <span className="graph-zoom-level">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(3.0, z * 1.2))}
            title="Phóng to (+)"
            aria-label="Phóng to"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 8h9M8 3.5v9" />
            </svg>
          </button>
          <span className="graph-zoom-divider" aria-hidden="true" />
          <button
            type="button"
            onClick={() => fitView()}
            title="Vừa khung: thấy cả môn"
            aria-label="Vừa khung"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" />
            </svg>
          </button>
          <button
            type="button"
            className="graph-zoom-text"
            onClick={() => {
              viewGoal.current = null;
              cancelAnimationFrame(viewFrame.current);
              viewFrame.current = 0;
              view.current = { zoom: 1, pan: { x: 60, y: 60 } };
              setZoom(1);
              setPan({ x: 60, y: 60 });
            }}
            title="Về 100% (0)"
            aria-label="Đặt lại góc nhìn"
          >
            Đặt lại
          </button>
        </div>
      </div>

      {cycleAlert && (
        <div className="graph-cycle-alert" role="alert">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 1.8 15 14H1z" />
            <path d="M8 6v3.6M8 11.6v.1" />
          </svg>
          <span>{cycleAlert}</span>
          <button
            type="button"
            onClick={() => {
              setCycleAlert(null);
              setActiveCycle(null);
            }}
            aria-label="Đóng cảnh báo"
          >
            ×
          </button>
        </div>
      )}

      <div className="graph-legend" aria-label="Chú thích">
        <span className="graph-legend-item">
          <i className="glyph glyph-topic" /> Chủ đề
        </span>
        <span className="graph-legend-item">
          <i className="glyph glyph-progress" /> Đang học
        </span>
        <span className="graph-legend-item">
          <i className="glyph glyph-done" /> Đã vững
        </span>
        <span className="graph-legend-item">
          <i className="glyph glyph-milestone" /> Mốc kiểm tra
        </span>
        <span className="graph-legend-item">
          <i className="glyph glyph-strict" /> Bắt buộc
        </span>
        <span className="graph-legend-item">
          <i className="glyph glyph-soft" /> Nên học trước
        </span>
        <span className="graph-legend-hint">
          <kbd>Shift</kbd> + kéo để nối hai chặng
        </span>
      </div>

      <div className="graph-keyboard-nodes" aria-label="Graph checkpoints">
        {nodes.map((node) => (
          <button
            key={node.id}
            onFocus={() => {
              setHoveredNodeId(node.id);
              focusNode(node.id);
            }}
            onClick={() => onSelect?.(node.id)}
          >
            {node.title}
          </button>
        ))}
      </div>
      {/* 2D Canvas */}
      <canvas
        ref={canvasRef}
        className="graph-canvas"
        style={{ touchAction: "none" }}
        onPointerDown={handleMouseDown}
        onPointerMove={handleMouseMove}
        onPointerUp={handleMouseUp}
        onPointerCancel={() => {
          pointers.current.clear();
          pinch.current = null;
          isDraggingNode.current = false;
          isPanning.current = false;
          isEdgeDragging.current = false;
        }}
        onLostPointerCapture={() => {
          isDraggingNode.current = false;
          isPanning.current = false;
          isEdgeDragging.current = false;
        }}
        onWheel={handleWheel}
      />
    </div>
  );
}
