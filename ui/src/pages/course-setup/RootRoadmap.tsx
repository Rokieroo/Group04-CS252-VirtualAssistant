import { useState, type CSSProperties } from "react";
import { Modal } from "../../components/Modal";
import { coursePoints, rootGeometry } from "./rootGeometry";
import "./root-graph.css";
export type RootCourse = {
  id: string;
  title: string;
  nodes: {
    id: string;
    title: string;
    description?: string;
    minutes?: number;
    status?: string;
  }[];
};
const colors = ["#7c5bf0", "#0caaa0", "#e99b36", "#3d8eea", "#e96da2"];
export function RootRoadmap({ courses }: { courses: RootCourse[] }) {
  const [selected, setSelected] = useState<string | null>(null),
    [geometry, setGeometry] = useState(false);
  const [detail, setDetail] = useState<{
    course: RootCourse;
    node: RootCourse["nodes"][number];
  } | null>(null);
  const [offsets, setOffsets] = useState<Record<string, number>>({});
  const geo = rootGeometry(courses.length),
    active = courses.find((c) => c.id === selected) || courses[0];
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
      <div className="root-layout">
        <section className="root-canvas card">
          <h2>ALL COURSES · ROOT GRAPH</h2>
          <p>
            {courses.length} course branches · From root to latest checkpoint
          </p>
          <div
            className="root-scroll"
            tabIndex={0}
            aria-label="Roadmap canvas, scroll horizontally on small screens"
          >
            <svg
              viewBox="0 0 860 520"
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
                  <path stroke="#3187ed" d="M764 85 Q-596 260 764 435" />
                  {geo.boundaries.slice(1, -1).map((angle, i) => {
                    const p = geo.point(angle, geo.maxRadius(angle));
                    return (
                      <path
                        key={i}
                        stroke="#9864e9"
                        d={`M84 260 L${p.x} ${p.y}`}
                      />
                    );
                  })}
                  {[140, 280, 420, 560, 680].map((r) => (
                    <path
                      key={r}
                      stroke="#e5ba35"
                      d={`M${84 + r * Math.cos(-0.24)} ${260 + r * Math.sin(-0.24)} A${r} ${r} 0 0 1 ${84 + r * Math.cos(0.24)} ${260 + r * Math.sin(0.24)}`}
                    />
                  ))}
                </g>
              )}
              {courses.map((course, i) => {
                const basePoints = coursePoints(
                  i,
                  courses.length,
                  course.nodes.length,
                );
                const points = basePoints.map((p, j) => {
                  const lane = geo.lane(i),
                    base = Math.atan2(p.y - 260, p.x - 84),
                    radius = Math.hypot(p.x - 84, p.y - 260);
                  const angle = Math.max(
                    lane.low + 0.001,
                    Math.min(
                      lane.high - 0.001,
                      base +
                        (offsets[course.id + ":" + course.nodes[j].id] || 0),
                    ),
                  );
                  return geo.point(
                    angle,
                    Math.min(radius, geo.maxRadius(angle) * 0.98),
                  );
                });
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
                      d={`M84 260 ${points.map((p) => `L${p.x} ${p.y}`).join(" ")}`}
                    />
                    {course.nodes.map((node, j) => {
                      const p = basePoints[j];
                      const key = course.id + ":" + node.id;
                      const baseAngle = Math.atan2(p.y - 260, p.x - 84),
                        r = Math.hypot(p.x - 84, p.y - 260),
                        lane = geo.lane(i);
                      const angle = Math.max(
                        lane.low + 0.001,
                        Math.min(
                          lane.high - 0.001,
                          baseAngle + (offsets[key] || 0),
                        ),
                      );
                      const position = geo.point(
                        angle,
                        Math.min(r, geo.maxRadius(angle) * 0.98),
                      );
                      return (
                        <g
                          key={node.id}
                          role="button"
                          tabIndex={0}
                          aria-label={`${course.title}: ${node.title}`}
                          className="root-node"
                          transform={`translate(${position.x} ${position.y})`}
                          onClick={() => showNode(course, node)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              showNode(course, node);
                            }
                          }}
                          onPointerDown={(e) => {
                            e.currentTarget.setPointerCapture(e.pointerId);
                            setSelected(course.id);
                          }}
                          onPointerMove={(e) => {
                            if (e.buttons !== 1) return;
                            const svg = e.currentTarget.ownerSVGElement;
                            if (!svg) return;
                            const rect = svg.getBoundingClientRect();
                            const y =
                              ((e.clientY - rect.top) * 520) / rect.height;
                            const delta =
                              Math.atan2(y - 260, p.x - 84) - baseAngle;
                            setOffsets((old) => ({ ...old, [key]: delta }));
                          }}
                          onPointerUp={() => showNode(course, node)}
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
                  cy="260"
                  r="30"
                  fill="white"
                  stroke="#d9d0ff"
                  strokeWidth="7"
                />
                <circle cx="84" cy="260" r="21" fill="#7455eb" />
                <text
                  x="84"
                  y="267"
                  textAnchor="middle"
                  fill="white"
                  fontSize="24"
                >
                  ✦
                </text>
                <text
                  x="84"
                  y="312"
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
