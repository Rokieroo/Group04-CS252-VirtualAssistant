import { useRef, type KeyboardEvent } from "react";
import type { Edge } from "../../api/core";
import { statusLabels } from "../../app/text";
import { byWeek, isMilestone, statusOf, type Step } from "./steps";

const COL = 236;
const ROW = 76;
const W = 188;
const H = 52;
const PAD = 28;
const HEAD = 34;
const arrows: Record<string, [number, number]> = {
  ArrowRight: [1, 0],
  ArrowLeft: [-1, 0],
  ArrowDown: [0, 1],
  ArrowUp: [0, -1],
};

/** Where every step sits: one column per week, steps stacked in the order of the timeline. */
export function layout(steps: Step[]) {
  const weeks = byWeek(steps);
  const at = new Map<string, { col: number; row: number; x: number; y: number }>();
  weeks.forEach((w, col) =>
    w.steps.forEach((step, row) =>
      at.set(step.id, { col, row, x: PAD + col * COL, y: HEAD + PAD + row * ROW }),
    ),
  );
  const rows = Math.max(1, ...weeks.map((w) => w.steps.length));
  return {
    weeks,
    at,
    width: PAD * 2 + Math.max(0, weeks.length - 1) * COL + W,
    height: HEAD + PAD * 2 + (rows - 1) * ROW + H,
  };
}

/** At most two lines of about ``max`` characters; the full title stays in the label and tooltip. */
function lines(title: string, max = 22): string[] {
  const out: string[] = [];
  let line = "";
  for (const word of title.split(/\s+/)) {
    if (line && `${line} ${word}`.length > max) {
      out.push(line);
      line = word;
    } else line = line ? `${line} ${word}` : word;
  }
  out.push(line);
  const cut = (text: string) => (text.length > max + 2 ? `${text.slice(0, max)}…` : text);
  return out.length > 2 ? [cut(out[0]), `${out[1].slice(0, max - 1).trimEnd()}…`] : out.map(cut);
}

/**
 * The prerequisite graph (issue #108): weeks left to right, a solid line for "must learn first",
 * a dashed one for week order. Static SVG: nothing animates at rest, and the page scrolls it.
 */
// shortcut: no zoom or minimap; the container scrolls. Add them when roadmaps pass ~30 steps.
export function GraphView({
  steps,
  edges,
  selectedId,
  onSelect,
}: {
  steps: Step[];
  edges: Edge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { weeks, at, width, height } = layout(steps);
  const nodes = useRef(new Map<string, SVGGElement>());
  const tabStop = selectedId && at.has(selectedId) ? selectedId : steps[0]?.id;

  // Arrow keys walk the grid: left/right change week, up/down move inside the week.
  const move = (event: KeyboardEvent, id: string) => {
    const here = at.get(id)!;
    const delta = arrows[event.key];
    if (!delta) return;
    event.preventDefault();
    const column = weeks[here.col + delta[0]]?.steps;
    const target = column?.[delta[0] ? Math.min(here.row, column.length - 1) : here.row + delta[1]];
    if (target) nodes.current.get(target.id)?.focus();
  };

  return (
    <div className="graph">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="group"
        aria-label="Sơ đồ lộ trình theo tuần. Dùng phím mũi tên để di chuyển giữa các bước."
      >
        <defs>
          <pattern id="graph-dots" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" className="graph-dot" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#graph-dots)" />

        {weeks.map((w, col) => (
          <text key={w.week} className="graph-week" x={PAD + col * COL} y={HEAD}>
            Tuần {w.week}
          </text>
        ))}

        {edges.map((edge) => {
          const from = at.get(edge.parent_id);
          const to = at.get(edge.child_id);
          if (!from || !to) return null;
          const forward = to.col > from.col;
          // Between weeks the line leaves the right side; inside a week it drops from the bottom.
          const [x1, y1] = forward ? [from.x + W, from.y + H / 2] : [from.x + W / 2, from.y + H];
          const [x2, y2] = forward ? [to.x, to.y + H / 2] : [to.x + W / 2, to.y];
          const bend = forward ? (x2 - x1) / 2 : 0;
          const drop = forward ? 0 : (y2 - y1) / 2;
          const on = edge.parent_id === selectedId || edge.child_id === selectedId;
          const name = `graph-edge ${edge.kind === "soft" ? "graph-edge-soft" : ""} ${on ? "graph-edge-on" : ""}`;
          return (
            <g key={`${edge.parent_id}>${edge.child_id}`} className={name}>
              <path
                d={`M${x1},${y1} C${x1 + bend},${y1 + drop} ${x2 - bend},${y2 - drop} ${x2},${y2}`}
              />
              <circle cx={x2} cy={y2} r="3" />
            </g>
          );
        })}

        {steps.map((step) => {
          const p = at.get(step.id)!;
          const status = statusOf(step);
          const text = lines(step.title);
          const selected = step.id === selectedId;
          return (
            <g
              key={step.id}
              ref={(node) => {
                if (node) nodes.current.set(step.id, node);
                else nodes.current.delete(step.id);
              }}
              className={`graph-node graph-${status} ${isMilestone(step) ? "graph-milestone" : ""}`}
              transform={`translate(${p.x},${p.y})`}
              role="button"
              tabIndex={step.id === tabStop ? 0 : -1}
              aria-pressed={selected}
              aria-label={`${isMilestone(step) ? "Mốc kiểm tra" : "Bước"}: ${step.title}, tuần ${step.week ?? 1}, ${statusLabels[status]}`}
              onClick={() => onSelect(step.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(step.id);
                } else move(event, step.id);
              }}
            >
              <title>{step.title}</title>
              <rect className="graph-box" width={W} height={H} rx="10" />
              {isMilestone(step) ? (
                <path className="graph-mark" d="M18 18 l8 8 -8 8 -8 -8z" />
              ) : (
                <circle className="graph-mark" cx="18" cy="26" r="6" />
              )}
              <text className="graph-title" x="34" y={text.length > 1 ? 22 : 30}>
                {text.map((line, i) => (
                  <tspan key={i} x="34" dy={i ? 16 : 0}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
