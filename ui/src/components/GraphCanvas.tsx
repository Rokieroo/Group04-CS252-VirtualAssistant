import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import "./GraphCanvas.css";

export interface GraphNode {
  id: string;
  title: string;
  type: "topic" | "milestone";
  week?: number | null;
  layer?: number | null;
  est_minutes?: number;
  status?: "not_started" | "in_progress" | "mastered" | "review_due";
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
  origin?: "week_order" | "llm" | "user";
  confidence?: number;
  reason?: string;
}

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layout?: "week" | "force";
  selectedId?: string | null;
  onSelect?: (nodeId: string | null) => void;
  onEdgeCreate?: (
    parentId: string,
    childId: string,
  ) => Promise<boolean | void> | boolean | void;
  onLayoutChange?: (
    positions: Array<{ node_id: string; x: number; y: number; pinned: boolean }>,
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

const STATUS_COLORS: Record<string, string> = {
  mastered: "#10b981", // emerald
  in_progress: "#3b82f6", // blue
  review_due: "#f59e0b", // amber
  not_started: "#64748b", // slate
};

export function GraphCanvas({
  nodes,
  edges,
  layout = "week",
  selectedId = null,
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

  // Initialize and place nodes
  useEffect(() => {
    const map = internalNodesRef.current;
    const newMap = new Map<string, InternalNode>();

    // Week column placement
    const colWidth = 180;
    const rowHeight = 85;

    // Group nodes by week
    const weekGroups = new Map<number, GraphNode[]>();
    for (const node of nodes) {
      const w = node.week ?? node.layer ?? 1;
      if (!weekGroups.has(w)) weekGroups.set(w, []);
      weekGroups.get(w)!.push(node);
    }

    nodes.forEach((node) => {
      const prev = map.get(node.id);
      const radius = getNodeRadius(node);
      let initX = prev?.displayX ?? node.x;
      let initY = prev?.displayY ?? node.y;

      if (initX === undefined || initY === undefined) {
        if (layout === "week") {
          const w = node.week ?? node.layer ?? 1;
          const list = weekGroups.get(w) || [node];
          const indexInWeek = list.findIndex((n) => n.id === node.id);
          initX = (w - 1) * colWidth + 80;
          initY = indexInWeek * rowHeight + 80;
        } else {
          // Circular / scatter distribution for force
          const angle = Math.random() * Math.PI * 2;
          const r = 100 + Math.random() * 250;
          initX = 400 + Math.cos(angle) * r;
          initY = 300 + Math.sin(angle) * r;
        }
      }

      newMap.set(node.id, {
        ...node,
        vx: 0,
        vy: 0,
        radius,
        displayX: initX,
        displayY: initY,
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

      if (layout === "force" && nodeList.length > 0) {
        // 1. Repulsion between all nodes
        for (let i = 0; i < nodeList.length; i++) {
          for (let j = i + 1; j < nodeList.length; j++) {
            const a = nodeList[i];
            const b = nodeList[j];
            const dx = b.displayX - a.displayX;
            const dy = b.displayY - a.displayY;
            const dist = Math.hypot(dx, dy) || 1;
            if (dist < 350) {
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
          }
        });
      }

      draw();
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

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(zoom, zoom);

    const nodeMap = internalNodesRef.current;
    const activeHover = hoveredNodeId || selectedId;

    // Determine neighbor nodes if a node is focused/hovered
    const neighborSet = new Set<string>();
    if (activeHover) {
      neighborSet.add(activeHover);
      edges.forEach((edge) => {
        if (edge.parent_id === activeHover) neighborSet.add(edge.child_id);
        if (edge.child_id === activeHover) neighborSet.add(edge.parent_id);
      });
    }

    // Set of edges belonging to the cycle
    const cycleEdgeSet = new Set<string>();
    if (activeCycle && activeCycle.length > 1) {
      for (let i = 0; i < activeCycle.length - 1; i++) {
        cycleEdgeSet.add(`${activeCycle[i]}>${activeCycle[i + 1]}`);
      }
    }

    // 1. Draw Week columns background if in week layout
    if (layout === "week") {
      const colWidth = 180;
      const maxWeek = Math.max(
        ...Array.from(nodeMap.values()).map((n) => n.week ?? n.layer ?? 1),
        1,
      );
      ctx.save();
      for (let w = 1; w <= maxWeek; w++) {
        const x = (w - 1) * colWidth + 10;
        ctx.fillStyle = w % 2 === 0 ? "rgba(241, 245, 249, 0.5)" : "transparent";
        ctx.fillRect(x, -500, colWidth, 2000);
        ctx.fillStyle = "#94a3b8";
        ctx.font = "bold 13px Inter, sans-serif";
        ctx.fillText(`Tuần ${w}`, x + 15, 25);
      }
      ctx.restore();
    }

    // 2. Draw Edges
    edges.forEach((edge) => {
      const parent = nodeMap.get(edge.parent_id);
      const child = nodeMap.get(edge.child_id);
      if (!parent || !child) return;

      const isCycleEdge = cycleEdgeSet.has(
        `${edge.parent_id}>${edge.child_id}`,
      );
      const isConnectedToFocus =
        !activeHover ||
        (neighborSet.has(edge.parent_id) && neighborSet.has(edge.child_id));

      ctx.save();
      ctx.beginPath();

      if (isCycleEdge) {
        ctx.strokeStyle = "#ef4444"; // Bold cycle red
        ctx.lineWidth = 3.5;
        ctx.setLineDash([]);
      } else {
        const alpha = isConnectedToFocus ? 0.85 : 0.12;
        ctx.lineWidth = edge.kind === "covers" ? 1.2 : 2;

        if (edge.kind === "soft") {
          ctx.strokeStyle = `rgba(148, 163, 184, ${alpha})`;
          ctx.setLineDash([5, 5]);
        } else if (edge.kind === "covers") {
          ctx.strokeStyle = `rgba(168, 85, 247, ${alpha})`;
          ctx.setLineDash([2, 4]);
        } else if (edge.origin === "llm") {
          ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`;
          ctx.setLineDash([6, 3]);
        } else {
          ctx.strokeStyle = `rgba(71, 85, 105, ${alpha})`;
          ctx.setLineDash([]);
        }
      }

      // Draw line from edge of parent to edge of child
      const dx = child.displayX - parent.displayX;
      const dy = child.displayY - parent.displayY;
      const dist = Math.hypot(dx, dy) || 1;
      const pRatio = parent.radius / dist;
      const cRatio = (child.radius + 6) / dist;

      const startX = parent.displayX + dx * pRatio;
      const startY = parent.displayY + dy * pRatio;
      const endX = child.displayX - dx * cRatio;
      const endY = child.displayY - dy * cRatio;

      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.stroke();

      // Directed arrow head
      const arrowSize = isCycleEdge ? 9 : 7;
      const angle = Math.atan2(dy, dx);
      ctx.fillStyle = isCycleEdge ? "#ef4444" : ctx.strokeStyle;
      ctx.beginPath();
      ctx.moveTo(
        child.displayX - dx * (child.radius / dist),
        child.displayY - dy * (child.radius / dist),
      );
      ctx.lineTo(
        endX - arrowSize * Math.cos(angle - Math.PI / 6),
        endY - arrowSize * Math.sin(angle - Math.PI / 6),
      );
      ctx.lineTo(
        endX - arrowSize * Math.cos(angle + Math.PI / 6),
        endY - arrowSize * Math.sin(angle + Math.PI / 6),
      );
      ctx.closePath();
      ctx.fill();

      // If hovered edge, draw confidence / reason tag
      if (hoveredEdge === edge) {
        const midX = (startX + endX) / 2;
        const midY = (startY + endY) / 2;
        const label = `${edge.kind ?? "strict"} · ${Math.round(
          (edge.confidence ?? 1) * 100,
        )}%`;
        ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
        ctx.fillRect(midX - 35, midY - 14, 70, 20);
        ctx.fillStyle = "#ffffff";
        ctx.font = "11px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(label, midX, midY);
      }

      ctx.restore();
    });

    // 3. Draw Rubber-band edge when dragging Shift+edge
    if (isEdgeDragging.current && edgeDragSource.current && edgeDragPos.current) {
      const src = nodeMap.get(edgeDragSource.current);
      if (src) {
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 2.5;
        ctx.setLineDash([4, 4]);
        ctx.moveTo(src.displayX, src.displayY);
        ctx.lineTo(edgeDragPos.current.x, edgeDragPos.current.y);
        ctx.stroke();
        ctx.restore();
      }
    }

    // 4. Draw Nodes
    nodeMap.forEach((node) => {
      const isSelected = selectedId === node.id;
      const isHovered = hoveredNodeId === node.id;
      const isCycle = activeCycle?.includes(node.id);
      const isNeighbor = !activeHover || neighborSet.has(node.id);

      ctx.save();
      const alpha = isNeighbor ? 1.0 : 0.2;
      ctx.globalAlpha = alpha;

      const fill = isCycle
        ? "#ef4444"
        : STATUS_COLORS[node.status || "not_started"] || "#64748b";

      ctx.fillStyle = fill;
      ctx.strokeStyle = isSelected
        ? "#0f172a"
        : isHovered
          ? "#2563eb"
          : "#ffffff";
      ctx.lineWidth = isSelected ? 3.5 : isHovered ? 2.5 : 1.5;

      ctx.beginPath();
      if (node.type === "milestone") {
        // Milestone: Diamond shape
        const r = node.radius * 1.15;
        ctx.moveTo(node.displayX, node.displayY - r);
        ctx.lineTo(node.displayX + r, node.displayY);
        ctx.lineTo(node.displayX, node.displayY + r);
        ctx.lineTo(node.displayX - r, node.displayY);
        ctx.closePath();
      } else {
        // Topic: Circle shape
        ctx.arc(node.displayX, node.displayY, node.radius, 0, Math.PI * 2);
      }
      ctx.fill();
      ctx.stroke();

      // Warning dot for insufficient sources
      if (node.sources_status === "insufficient") {
        ctx.beginPath();
        const dotX = node.displayX + node.radius * 0.7;
        const dotY = node.displayY - node.radius * 0.7;
        ctx.arc(dotX, dotY, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = "#f59e0b"; // Warning amber
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Title label below node
      ctx.globalAlpha = isNeighbor ? 1.0 : 0.3;
      ctx.font = isSelected
        ? "bold 12px Inter, sans-serif"
        : "11px Inter, sans-serif";
      ctx.fillStyle = "#1e293b";
      ctx.textAlign = "center";
      const shortTitle =
        node.title.length > 22
          ? node.title.slice(0, 20) + "…"
          : node.title;
      ctx.fillText(
        shortTitle,
        node.displayX,
        node.displayY + node.radius + 14,
      );

      ctx.restore();
    });

    ctx.restore();
  }, [
    pan,
    zoom,
    edges,
    hoveredNodeId,
    hoveredEdge,
    selectedId,
    activeCycle,
    layout,
  ]);

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

  // Mouse & Touch Interaction Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
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
      clickedNode.pinned = true;
      onSelect?.(clickedNode.id);
    } else {
      // Background pan
      isPanning.current = true;
      panStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
      onSelect?.(null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = screenToCanvas(e.clientX, e.clientY);

    if (isEdgeDragging.current) {
      edgeDragPos.current = { x, y };
      return;
    }

    if (isDraggingNode.current && draggedNodeId.current) {
      const node = internalNodesRef.current.get(draggedNodeId.current);
      if (node) {
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
          onLayoutChange?.(positions);
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
  };

  const handleMouseUp = async (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isEdgeDragging.current && edgeDragSource.current) {
      const { x, y } = screenToCanvas(e.clientX, e.clientY);
      const targetNode = findNodeAt(x, y);

      if (targetNode && targetNode.id !== edgeDragSource.current) {
        const parentId = edgeDragSource.current;
        const childId = targetNode.id;

        // Client-side cycle detection
        const detectedCycle = findCyclePath(edges, parentId, childId);
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
            }
          }
        }
      }

      isEdgeDragging.current = false;
      edgeDragSource.current = null;
      edgeDragPos.current = null;
    }

    if (isDraggingNode.current) {
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
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((prev) => Math.max(0.2, Math.min(3.0, prev * factor)));
  };

  // Keyboard navigation (+ - arrow keys 0)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
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
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
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
      {/* Interactive Toolbar */}
      <div className="graph-toolbar">
        <div className="layout-toggle">
          <button
            type="button"
            className={layout === "week" ? "active" : ""}
            onClick={() => onLayoutModeChange?.("week")}
            title="Sắp xếp theo tuần syllabus"
          >
            Theo tuần
          </button>
          <button
            type="button"
            className={layout === "force" ? "active" : ""}
            onClick={() => onLayoutModeChange?.("force")}
            title="Sắp xếp lực đồ thị kiểu Obsidian"
          >
            Lực (Obsidian)
          </button>
        </div>

        <div className="zoom-controls">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(3.0, z * 1.2))}
            title="Phóng to (+)"
            aria-label="Phóng to"
          >
            +
          </button>
          <span className="zoom-level">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.2, z * 0.8))}
            title="Thu nhỏ (-)"
            aria-label="Thu nhỏ"
          >
            -
          </button>
          <button
            type="button"
            onClick={() => {
              setZoom(1);
              setPan({ x: 60, y: 60 });
            }}
            title="Vừa màn hình (0)"
            aria-label="Đặt lại góc nhìn"
          >
            Đặt lại
          </button>
        </div>
      </div>

      {/* Cycle rejection alert */}
      {cycleAlert && (
        <div className="cycle-alert-banner" role="alert">
          <span className="cycle-icon">⚠️</span>
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

      {/* Helper guide */}
      <div className="graph-canvas-hint">
        <span>Giữ <strong>Shift + Kéo</strong> để tạo liên kết tiên quyết</span>
      </div>

      {/* 2D Canvas */}
      <canvas
        ref={canvasRef}
        className="graph-canvas"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
      />
    </div>
  );
}
