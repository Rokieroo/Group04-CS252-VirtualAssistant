import { useState } from "react";
import type { RoadmapDraft, SyllabusDraft } from "../../api/core";
import { NodeMaterials } from "./NodeMaterials";

type Props = {
  roadmap: RoadmapDraft;
  draft: SyllabusDraft | null;
  weekly: number;
  onWeeklyChange: (minutes: number) => void;
  /** The roadmap is saved on the backend, so its nodes have sources to show. */
  live?: boolean;
};

/** S5 overview and selected-week detail share the same approved syllabus data. */
export function RoadmapTimeline({
  roadmap,
  draft,
  weekly,
  onWeeklyChange,
  live = false,
}: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const weeks = [...new Set(roadmap.nodes.map((n) => n.week ?? 1))].sort(
    (a, b) => a - b,
  );
  const nodes = roadmap.nodes.filter((n) => (n.week ?? 1) === selected);
  const milestones = roadmap.nodes.filter((n) => n.type === "milestone");
  return (
    <div className="core-roadmap-columns">
      <section className="card core-panel">
        <div>
          <h3>Learning path by week</h3>
          <p>Select a week to inspect topics and prerequisites.</p>
        </div>
        <div className="core-week-grid">
          {weeks.map((week) => {
            const items = roadmap.nodes.filter((n) => (n.week ?? 1) === week);
            return (
              <button
                key={week}
                className={`core-week ${selected === week ? "selected" : ""}`}
                aria-pressed={selected === week}
                onClick={() => setSelected(week)}
              >
                <span className="core-week-number">
                  {String(week).padStart(2, "0")}
                </span>
                <span>
                  <strong>
                    Week {week}
                    {items.some((n) => n.type === "milestone")
                      ? " · Milestone"
                      : ""}
                  </strong>
                  <small>
                    {items
                      .map(
                        (n) =>
                          `${n.title} · ${n.est_minutes ?? n.duration_minutes ?? 0} min · ${n.status || "available"}`,
                      )
                      .join(" · ")}
                  </small>
                </span>
              </button>
            );
          })}
        </div>
        {selected !== null && (
          <section
            className="core-week-detail"
            aria-label={`Week ${selected} details`}
          >
            <h3>Week {selected} · Details</h3>
            {nodes.map((node) => (
              <div key={node.id}>
                <strong>{node.title}</strong>
                <p
                  className={`roadmap-status status-${node.status || "available"}`}
                >
                  {
                    {
                      locked: "Locked",
                      available: "Available",
                      in_progress: "In progress",
                      done: "Done",
                      needs_review: "Needs review",
                    }[node.status || "available"]
                  }
                </p>
                <p>{node.est_minutes ?? node.duration_minutes ?? 0} minutes</p>
                <p>
                  Prerequisites:{" "}
                  {roadmap.edges
                    .filter((e) => e.child_id === node.id)
                    .map(
                      (e) =>
                        roadmap.nodes.find((n) => n.id === e.parent_id)?.title,
                    )
                    .join(", ") || "None specified"}
                </p>
                {live && node.type !== "milestone" && <NodeMaterials nodeId={node.id} />}
              </div>
            ))}
          </section>
        )}
      </section>
      <aside className="card core-panel core-plan-settings">
        <h3>Plan settings</h3>
        <label>
          Weekly study time (minutes)
          <input
            type="number"
            min="25"
            max="10080"
            value={weekly}
            onChange={(e) => onWeeklyChange(Number(e.target.value))}
          />
        </label>
        <div>
          <span className="core-field-label">Planned duration</span>
          <strong>{Math.max(...weeks, 0)} weeks</strong>
        </div>
        <hr />
        <div>
          <span className="core-field-label">Milestones</span>
          {milestones.map((n) => (
            <p className="core-milestone" key={n.id}>
              {n.title} · Week {n.week}
            </p>
          ))}
        </div>
        <div>
          <span className="core-field-label">Learning goals</span>
          <ul>
            {draft?.outcomes.map((o) => (
              <li key={o.code}>{o.description}</li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
