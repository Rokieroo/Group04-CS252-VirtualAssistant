import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { topologicalNodes } from "../../api/graphState";
import { Modal } from "../../components/Modal";
import { rootLayout, type PolarPosition } from "./rootGeometry";
import "./root-graph.css";
export type RootCourse = {
  id: string;
  title: string;
  edges?: { parent_id: string; child_id: string }[];
  nodes: {
    id: string;
    title: string;
    description?: string;
    minutes?: number;
    status?: string;
    week?: number | null;
    covers?: string[];
  }[];
};
/** Existing Kahn helper, with original array order as the same-week tie-breaker. */
export function orderRootCourse(course: RootCourse) {
  const edges = [
    ...(course.edges || []),
    ...course.nodes.flatMap((node) =>
      (node.covers || []).map((parent_id) => ({
        parent_id,
        child_id: node.id,
      })),
    ),
  ];
  const originals = new Map(course.nodes.map((n) => [n.id, n]));
  const nodes = topologicalNodes(
    course.nodes.map((n, i) => ({ ...n, title: String(i).padStart(12, "0") })),
    edges,
  ).map((n) => originals.get(n.id)!);
  const indices = new Map(nodes.map((n, i) => [n.id, i]));
  const valid =
    originals.size === course.nodes.length &&
    edges.every(
      (e) =>
        !indices.has(e.parent_id) ||
        !indices.has(e.child_id) ||
        indices.get(e.parent_id)! < indices.get(e.child_id)!,
    );
  return { ...course, nodes: valid ? nodes : [], invalid: !valid };
}
const colors = ["#7c5bf0", "#0caaa0", "#e99b36", "#3d8eea", "#e96da2"];
export function RootRoadmap({
  courses: inputCourses,
}: {
  courses: RootCourse[];
}) {
  const courses = useMemo(
    () => inputCourses.map(orderRootCourse),
    [inputCourses],
  );
  const [selected, setSelected] = useState<string | null>(null),
    [geometry, setGeometry] = useState(false);
  const [detail, setDetail] = useState<{
    course: RootCourse;
    node: RootCourse["nodes"][number];
  } | null>(null);
  const [offsets, setOffsets] = useState<Record<string, PolarPosition>>({});
  const layout = useMemo(
    () => rootLayout(courses.map((c) => c.nodes.length)),
    [courses],
  );
  const geo = layout.geo;
  const scroll = useRef<HTMLDivElement>(null);
  const dragging = useRef<{ key: string; pointer: number } | null>(null);
  useEffect(() => {
    if (scroll.current)
      scroll.current.scrollTop = Math.max(
        0,
        geo.origin.y - scroll.current.clientHeight / 2,
      );
  }, [geo.height]);
  const active = courses.find((c) => c.id === selected) || courses[0];
  const total = courses.reduce((n, c) => n + c.nodes.length, 0);
  const showNode = (course: RootCourse, node: RootCourse["nodes"][number]) => {
    setSelected(course.id);
    setDetail({ course, node });
  };
  return (
    <section className="root-universe" aria-label="All courses root roadmap">
      <header className="root-heading">
        <div>
          <h1>Your learning universe</h1>
          <p>
            Every course begins at one point. Explore all learning paths
            together.
          </p>
        </div>
        <button aria-pressed={geometry} onClick={() => setGeometry(!geometry)}>
          {geometry ? "Hide" : "Show"} geometry
        </button>
      </header>
      {courses
        .filter((c) => c.invalid)
        .map((c) => (
          <p role="alert" key={c.id}>
            Cannot draw {c.title}: its prerequisites contain a cycle or
            duplicate checkpoints. Correct the course graph before viewing its
            path.
          </p>
        ))}
      <div className="root-layout">
        <section className="root-canvas card">
          <h2>ALL COURSES · ROOT GRAPH</h2>
          <p>
            {courses.length} course branches · From root to latest checkpoint
          </p>
          <div
            className="root-scroll"
            ref={scroll}
            tabIndex={0}
            aria-label="Roadmap canvas, scroll to explore the roadmap"
          >
            <svg
              viewBox={`0 0 ${geo.width} ${geo.height}`}
              style={{ minWidth: geo.width }}
              className="root-svg"
              aria-label={`${courses.length} course paths from one starting point`}
            >
              {geometry && (
                <g
                  fill="none"
                  strokeWidth="1"
                  strokeDasharray="5 5"
                  opacity=".65"
                >
                  <path stroke="#3187ed" d={geo.parabola} />
                  {geo.boundaries.slice(1, -1).map((angle, i) => {
                    const p = geo.point(angle, geo.maxRadius(angle));
                    return (
                      <path
                        key={i}
                        stroke="#9864e9"
                        d={`M84 ${geo.origin.y} L${p.x} ${p.y}`}
                      />
                    );
                  })}
                  {layout.courses.flatMap((c, i) =>
                    c.bands.flatMap((b, j) =>
                      [b.low, b.high].map((r, k) => {
                        const a = geo.point(c.lowAngle, r),
                          z = geo.point(c.highAngle, r);
                        return (
                          <path
                            key={`${i}-${j}-${k}`}
                            stroke="#e5ba35"
                            d={`M${a.x} ${a.y} A${r} ${r} 0 0 1 ${z.x} ${z.y}`}
                          />
                        );
                      }),
                    ),
                  )}
                </g>
              )}
              {courses.map((course, i) => {
                const points = course.nodes.map((node, j) =>
                  layout.project(i, j, offsets[course.id + ":" + node.id]),
                );
                const color = colors[i % colors.length];
                const last = points.at(-1);
                return (
                  <g
                    key={course.id}
                    data-course-path={course.id}
                    style={{ color }}
                  >
                    <path
                      className="root-course-line"
                      stroke={color}
                      fill="none"
                      strokeWidth={active?.id === course.id ? 3.5 : 2.5}
                      d={`M84 ${geo.origin.y} ${points.map((p) => `L${p.x} ${p.y}`).join(" ")}`}
                    />
                    {course.nodes.map((node, j) => {
                      const key = course.id + ":" + node.id;
                      const position = points[j];
                      const band = layout.courses[i].bands[j];
                      return (
                        <g
                          key={node.id}
                          role="button"
                          tabIndex={0}
                          aria-label={`${course.title}: ${node.title}`}
                          className="root-node"
                          data-low-radius={band.low}
                          data-high-radius={band.high}
                          data-radius={position.radius}
                          data-angle={position.angle}
                          transform={`translate(${position.x} ${position.y})`}
                          onClick={() => showNode(course, node)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              showNode(course, node);
                            }
                          }}
                          onPointerDown={(e) => {
                            dragging.current = { key, pointer: e.pointerId };
                            e.currentTarget.setPointerCapture(e.pointerId);
                            setSelected(course.id);
                          }}
                          onPointerMove={(e) => {
                            if (
                              dragging.current?.key !== key ||
                              dragging.current.pointer !== e.pointerId
                            )
                              return;
                            const matrix =
                              e.currentTarget.ownerSVGElement?.getScreenCTM();
                            if (!matrix) return;
                            const p = new DOMPoint(
                              e.clientX,
                              e.clientY,
                            ).matrixTransform(matrix.inverse());
                            const constrained = layout.project(i, j, {
                              angle: Math.atan2(
                                p.y - geo.origin.y,
                                p.x - geo.origin.x,
                              ),
                              radius: Math.hypot(
                                p.x - geo.origin.x,
                                p.y - geo.origin.y,
                              ),
                            });
                            setOffsets((old) => ({
                              ...old,
                              [key]: constrained,
                            }));
                          }}
                          onPointerCancel={() => {
                            dragging.current = null;
                          }}
                          onLostPointerCapture={() => {
                            dragging.current = null;
                          }}
                          onPointerUp={(e) => {
                            if (
                              dragging.current?.key !== key ||
                              dragging.current.pointer !== e.pointerId
                            )
                              return;
                            dragging.current = null;
                            e.currentTarget.releasePointerCapture(e.pointerId);
                            showNode(course, node);
                          }}
                        >
                          <title>{node.title}</title>
                          <circle r="12" fill={color} opacity=".17" />
                          <circle
                            r="6.5"
                            fill={node.status === "done" ? color : "white"}
                            stroke={color}
                            strokeWidth="2"
                          />
                          <circle
                            r="2"
                            fill={node.status === "done" ? "white" : color}
                          />
                        </g>
                      );
                    })}
                    {last && (
                      <text
                        x={Math.max(150, last.x - 110)}
                        y={last.y - 18}
                        fill={color}
                        fontSize="11"
                        fontWeight="600"
                      >
                        {course.title.length > 23
                          ? course.title.slice(0, 22) + "…"
                          : course.title}
                      </text>
                    )}
                  </g>
                );
              })}
              <g aria-label="Your starting point">
                <circle
                  cx="84"
                  cy={geo.origin.y}
                  r="30"
                  fill="white"
                  stroke="#d9d0ff"
                  strokeWidth="7"
                />
                <circle cx="84" cy={geo.origin.y} r="21" fill="#7455eb" />
                <text
                  x="84"
                  y={geo.origin.y + 7}
                  textAnchor="middle"
                  fill="white"
                  fontSize="24"
                >
                  ✦
                </text>
                <text
                  x="84"
                  y={geo.origin.y + 52}
                  textAnchor="middle"
                  fill="#7155da"
                  fontSize="10"
                  fontWeight="700"
                >
                  YOUR STARTING POINT
                </text>
              </g>
            </svg>
          </div>
          <div className="root-selection">
            <small>SELECTED COURSE</small>
            <p>
              {active
                ? `${active.title} · Click or drag a checkpoint to read its description.`
                : "No courses yet. Enroll in Getting Started in Library or approve a course roadmap."}
            </p>
          </div>
        </section>
        <aside className="root-legend card">
          <h2>Course paths</h2>
          <p>{courses.length} active courses</p>
          {courses.map((c, i) => {
            const done = c.nodes.filter((n) => n.status === "done").length;
            return (
              <button
                key={c.id}
                className="root-course-card"
                style={
                  {
                    "--course-color": colors[i % colors.length],
                  } as CSSProperties
                }
                aria-pressed={active?.id === c.id}
                onClick={() => setSelected(c.id)}
              >
                <strong>
                  <span className="root-swatch" />
                  {c.title}
                </strong>
                <small>
                  {done}/{c.nodes.length} checkpoints completed
                </small>
                <progress max={c.nodes.length || 1} value={done} />
              </button>
            );
          })}
        </aside>
      </div>
      <footer className="root-summary card">
        <strong>One starting point</strong>
        <strong>{courses.length} courses</strong>
        <strong>{total} learning checkpoints</strong>
        <p>All courses share a root, but each follows its own learning path.</p>
      </footer>
      {detail && (
        <Modal title={detail.node.title} onClose={() => setDetail(null)}>
          <p>{detail.course.title}</p>
          <p>
            {detail.node.description ||
              "Review this checkpoint in your course roadmap to explore its prerequisites and learning materials."}
          </p>
          {detail.node.minutes !== undefined && (
            <p>{detail.node.minutes} minutes</p>
          )}
          <button onClick={() => setDetail(null)}>Close description</button>
        </Modal>
      )}
    </section>
  );
}
