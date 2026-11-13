import { duration, statusLabels } from "../../app/text";
import { byWeek, isMilestone, minutesOf, statusOf, type Step } from "./steps";

/**
 * The roadmap as a route: one line down the page, a station per week, a stop per step.
 * It is a plain list of buttons, so it is also the keyboard and screen-reader view of the graph.
 */
export function RouteTimeline({
  steps,
  selectedId,
  onSelect,
}: {
  steps: Step[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ol className="route" aria-label="Lộ trình theo tuần">
      {byWeek(steps).map(({ week, steps: stops }) => {
        const topics = stops.filter((s) => !isMilestone(s));
        const done = topics.length > 0 && topics.every((s) => statusOf(s) === "done");
        return (
          <li key={week} className={`route-week ${done ? "route-week-done" : ""}`}>
            <h2 className="route-station">Tuần {week}</h2>
            <ul className="route-stops">
              {stops.map((step) => {
                const status = statusOf(step);
                return (
                  <li key={step.id}>
                    <button
                      type="button"
                      className={`route-stop route-${status} ${isMilestone(step) ? "route-milestone" : ""}`}
                      aria-pressed={step.id === selectedId}
                      onClick={() => onSelect(step.id)}
                    >
                      <span className="route-mark" aria-hidden="true" />
                      <span className="route-title">{step.title}</span>
                      <span className="route-meta">
                        {isMilestone(step) && <span className="chip chip-signal">Mốc kiểm tra</span>}
                        {status !== "available" && (
                          <span className={`chip ${status === "locked" ? "" : "chip-route"}`}>
                            {statusLabels[status]}
                          </span>
                        )}
                        {!isMilestone(step) && minutesOf(step) > 0 && (
                          <span className="muted small">{duration(minutesOf(step))}</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
