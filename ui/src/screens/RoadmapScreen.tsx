import { useState } from "react";
import { duration } from "../app/text";
import type { Course } from "../app/useCourse";
import { Empty, Notice, PageHead } from "../ui/kit";
import { GraphView } from "./roadmap/GraphView";
import { RouteTimeline } from "./roadmap/RouteTimeline";
import { StepPanel } from "./roadmap/StepPanel";
import { isMilestone, minutesOf } from "./roadmap/steps";

const views = [
  ["route", "Lộ trình"],
  ["graph", "Sơ đồ"],
] as const;

/** The roadmap in two views with the step panel beside it. Shared by the proposal and the approved roadmap. */
export function RoadmapView({ course }: { course: Course }) {
  const [view, setView] = useState<(typeof views)[number][0]>("route");
  const roadmap = course.roadmap;
  if (!roadmap) return null;
  const selected = roadmap.nodes.find((n) => n.id === course.selectedId) ?? null;
  const topics = roadmap.nodes.filter((n) => !isMilestone(n));
  const total = topics.reduce((sum, n) => sum + minutesOf(n), 0);

  return (
    <div className={`roadmap ${selected ? "roadmap-open" : ""}`}>
      <div className="roadmap-main">
        <div className="roadmap-tools">
          <div className="segmented" role="group" aria-label="Cách xem lộ trình">
            {views.map(([id, label]) => (
              <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
                {label}
              </button>
            ))}
          </div>
          <p className="muted small">
            {topics.length} bước học, {roadmap.nodes.length - topics.length} mốc kiểm tra
            {total > 0 && `, khoảng ${duration(total)}`}
          </p>
        </div>

        {roadmap.overloaded_weeks.length > 0 && (
          <Notice tone="warn" title="Có tuần quá tải">
            Tuần {roadmap.overloaded_weeks.join(", ")} nhiều việc hơn thời gian học bạn đặt ra.
          </Notice>
        )}

        {view === "route" ? (
          <RouteTimeline steps={roadmap.nodes} selectedId={course.selectedId} onSelect={course.setSelectedId} />
        ) : (
          <>
            <GraphView
              steps={roadmap.nodes}
              edges={roadmap.edges}
              selectedId={course.selectedId}
              onSelect={course.setSelectedId}
            />
            <ul className="legend" aria-label="Chú giải sơ đồ">
              <li>
                <span className="legend-line" aria-hidden="true" />
                Phải học trước
              </li>
              <li>
                <span className="legend-line legend-soft" aria-hidden="true" />
                Thứ tự theo tuần
              </li>
              <li>
                <span className="legend-diamond" aria-hidden="true" />
                Mốc kiểm tra
              </li>
            </ul>
          </>
        )}
      </div>

      {selected && (
        <StepPanel course={course} step={selected} onClose={() => course.setSelectedId(null)} />
      )}
    </div>
  );
}

export function RoadmapScreen({ course }: { course: Course }) {
  if (!course.roadmap)
    return (
      <>
        <PageHead title="Lộ trình" />
        <Empty
          icon="roadmap"
          title="Chưa có lộ trình"
          action={
            <a className="btn btn-primary btn-md" href="#course">
              Bắt đầu từ đề cương
            </a>
          }
        >
          Lộ trình được dựng từ đề cương môn học: mỗi chủ đề là một bước, mỗi bài kiểm tra là một mốc.
        </Empty>
      </>
    );
  return (
    <>
      <PageHead
        title="Lộ trình"
        lead={
          course.stage === "ready"
            ? "Chọn một bước để xem cần học gì trước và học từ nguồn nào."
            : "Đây là lộ trình đề xuất. Duyệt nó ở mục Môn học để bắt đầu."
        }
      />
      <RoadmapView course={course} />
    </>
  );
}
