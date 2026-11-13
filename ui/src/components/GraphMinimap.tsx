import React, { useRef } from "react";
import type { GraphEdge, GraphNode, GraphPalette } from "./GraphCanvas";

export const MINIMAP_THRESHOLD = 30;
export const MINIMAP_WIDTH = 168;
export const MINIMAP_HEIGHT = 104;

const MINIMAP_PADDING = 10;
const WORLD_MARGIN = 36;

export interface MinimapNode {
  id: string;
  displayX: number;
  displayY: number;
  radius: number;
  type: GraphNode["type"];
  status?: GraphNode["status"];
}

export interface MinimapTransform {
  cx: number;
  cy: number;
  scale: number;
  width: number;
  height: number;
}

export interface DrawMinimapParams {
  nodes: MinimapNode[];
  edges: GraphEdge[];
  viewW: number;
  viewH: number;
  pan: { x: number; y: number };
  zoom: number;
  palette: GraphPalette;
  selectedId?: string | null;
  highlightedIds?: string[];
}

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

/** Computes world <-> minimap linear transform fitted to all graph nodes. */
export function computeMinimapTransform(
  nodes: MinimapNode[],
  width: number,
  height: number,
): MinimapTransform | null {
  if (!nodes.length || width <= 0 || height <= 0) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    const r = Number.isFinite(n.radius) ? n.radius : 18;
    if (n.displayX - r < minX) minX = n.displayX - r;
    if (n.displayX + r > maxX) maxX = n.displayX + r;
    if (n.displayY - r < minY) minY = n.displayY - r;
    if (n.displayY + r > maxY) maxY = n.displayY + r;
  }
  const x0 = minX - WORLD_MARGIN;
  const x1 = maxX + WORLD_MARGIN;
  const y0 = minY - WORLD_MARGIN;
  const y1 = maxY + WORLD_MARGIN;
  const spanX = Math.max(x1 - x0, 120);
  const spanY = Math.max(y1 - y0, 120);
  const usableW = Math.max(1, width - MINIMAP_PADDING * 2);
  const usableH = Math.max(1, height - MINIMAP_PADDING * 2);
  const scale = Math.min(usableW / spanX, usableH / spanY);
  return {
    cx: (x0 + x1) / 2,
    cy: (y0 + y1) / 2,
    scale,
    width,
    height,
  };
}

/** Converts a minimap CSS-pixel position back into canvas world coordinates. */
export function minimapPointToWorld(
  offsetX: number,
  offsetY: number,
  nodes: MinimapNode[],
  width: number,
  height: number,
): { x: number; y: number } | null {
  const tf = computeMinimapTransform(nodes, width, height);
  if (!tf) return null;
  return {
    x: tf.cx + (offsetX - tf.width / 2) / tf.scale,
    y: tf.cy + (offsetY - tf.height / 2) / tf.scale,
  };
}

/** Renders the graph overview and current viewport indicator onto the minimap canvas. */
export function drawMinimap(
  canvas: HTMLCanvasElement,
  {
    nodes,
    edges,
    viewW,
    viewH,
    pan,
    zoom,
    palette: c,
    selectedId = null,
    highlightedIds = [],
  }: DrawMinimapParams,
): void {
  const rect = canvas.getBoundingClientRect();
  const cssW = rect.width || canvas.clientWidth || MINIMAP_WIDTH;
  const cssH = rect.height || canvas.clientHeight || MINIMAP_HEIGHT;
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const targetW = Math.round(cssW * dpr);
  const targetH = Math.round(cssH * dpr);
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.save();
  if (typeof ctx.setTransform === "function") {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  ctx.clearRect(0, 0, cssW, cssH);

  const tf = computeMinimapTransform(nodes, cssW, cssH);
  if (!tf) {
    ctx.restore();
    return;
  }

  const toX = (wx: number) => tf.width / 2 + (wx - tf.cx) * tf.scale;
  const toY = (wy: number) => tf.height / 2 + (wy - tf.cy) * tf.scale;

  const byId = new Map<string, MinimapNode>();
  for (const node of nodes) byId.set(node.id, node);

  // Edges
  ctx.strokeStyle = withAlpha(c.edge, 0.35);
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  for (const edge of edges) {
    const parent = byId.get(edge.parent_id);
    const child = byId.get(edge.child_id);
    if (!parent || !child) continue;
    ctx.moveTo(toX(parent.displayX), toY(parent.displayY));
    ctx.lineTo(toX(child.displayX), toY(child.displayY));
  }
  ctx.stroke();

  // Nodes
  const focusSet = new Set(highlightedIds);
  if (selectedId) focusSet.add(selectedId);

  for (const node of nodes) {
    const mx = toX(node.displayX);
    const my = toY(node.displayY);
    const isFocused = focusSet.has(node.id);
    if (isFocused) {
      ctx.fillStyle = c.accent;
    } else if (node.status === "mastered") {
      ctx.fillStyle = c.success;
    } else if (
      node.status === "in_progress" ||
      node.status === "review_due"
    ) {
      ctx.fillStyle = c.accent;
    } else {
      ctx.fillStyle = node.type === "milestone" ? c.ink : c.muted;
    }

    if (node.type === "milestone" && typeof ctx.rotate === "function") {
      const half = isFocused ? 3.2 : 2.4;
      ctx.save();
      ctx.translate(mx, my);
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-half, -half, half * 2, half * 2);
      ctx.restore();
    } else if (node.type === "milestone") {
      const half = isFocused ? 3.2 : 2.4;
      ctx.fillRect(mx - half, my - half, half * 2, half * 2);
    } else {
      ctx.beginPath();
      ctx.arc(mx, my, isFocused ? 3 : 2.1, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Viewport rectangle
  if (viewW > 0 && viewH > 0 && zoom > 0) {
    const vpLeft = toX(-pan.x / zoom);
    const vpTop = toY(-pan.y / zoom);
    const vpWidth = Math.max(8, (viewW / zoom) * tf.scale);
    const vpHeight = Math.max(6, (viewH / zoom) * tf.scale);
    ctx.fillStyle = withAlpha(c.accent, 0.12);
    ctx.strokeStyle = c.accent;
    ctx.lineWidth = 1.5;
    ctx.fillRect(vpLeft, vpTop, vpWidth, vpHeight);
    if (typeof ctx.strokeRect === "function") {
      ctx.strokeRect(vpLeft, vpTop, vpWidth, vpHeight);
    }
  }

  ctx.restore();
}

export interface GraphMinimapProps {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  nodeCount: number;
  onNavigate: (
    offsetX: number,
    offsetY: number,
    width: number,
    height: number,
  ) => void;
}

export function GraphMinimap({
  canvasRef,
  nodeCount,
  onNavigate,
}: GraphMinimapProps) {
  const isScrubbing = useRef(false);

  const navigateFromEvent = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const width = rect.width || el.clientWidth || MINIMAP_WIDTH;
    const height = rect.height || el.clientHeight || MINIMAP_HEIGHT;
    const offsetX = Math.max(0, Math.min(width, e.clientX - rect.left));
    const offsetY = Math.max(0, Math.min(height, e.clientY - rect.top));
    onNavigate(offsetX, offsetY, width, height);
  };

  return (
    <div
      className="graph-minimap"
      role="group"
      aria-label="Bản đồ tổng quan đồ thị"
    >
      <span className="graph-minimap-label">Tổng quan ({nodeCount})</span>
      <canvas
        ref={canvasRef}
        className="graph-minimap-canvas"
        // A pointer shortcut only; keyboard and screen-reader users have the list view.
        aria-hidden="true"
        title="Nhấn hoặc kéo để di chuyển góc nhìn"
        style={{ touchAction: "none" }}
        onPointerDown={(e) => {
          e.stopPropagation();
          isScrubbing.current = true;
          e.currentTarget.setPointerCapture?.(e.pointerId);
          navigateFromEvent(e);
        }}
        onPointerMove={(e) => {
          if (!isScrubbing.current) return;
          e.stopPropagation();
          navigateFromEvent(e);
        }}
        onPointerUp={(e) => {
          isScrubbing.current = false;
          if (e.currentTarget.hasPointerCapture?.(e.pointerId)) {
            e.currentTarget.releasePointerCapture?.(e.pointerId);
          }
        }}
        onPointerCancel={() => {
          isScrubbing.current = false;
        }}
        onLostPointerCapture={() => {
          isScrubbing.current = false;
        }}
      />
    </div>
  );
}
