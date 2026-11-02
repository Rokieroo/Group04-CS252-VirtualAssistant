import type { Dispatch, SetStateAction } from "react";
import { Button } from "../../components/Button";
import { courseFor } from "../selectors";
import type { Session, State } from "../domain";
import { formatted } from "../../format";
import { addDays, dateKey, today } from "../../time";

type Props = {
  state: State;
  openLesson: (session: Session) => void;
  anchor: Date;
  setAnchor: Dispatch<SetStateAction<Date>>;
  view: string;
  setView: (view: string) => void;
};
export function SchedulePage({
  state,
  openLesson,
  anchor,
  setAnchor,
  view,
  setView,
}: Props) {
  const start = addDays(anchor, -((anchor.getDay() + 6) % 7));
  const calendarDays =
    view === "Week"
      ? Array.from({ length: 7 }, (_, i) => addDays(start, i))
      : Array.from({ length: 42 }, (_, i) => {
          const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
          return addDays(first, i - ((first.getDay() + 6) % 7));
        });

  return (
    <>
      <div className="toolbar">
        <Button
          onClick={() =>
            setAnchor((d) =>
              view === "Week"
                ? addDays(d, -7)
                : new Date(d.getFullYear(), d.getMonth() - 1, 1),
            )
          }
        >
          ‹ Previous
        </Button>
        <strong>
          {view === "Week"
            ? `${formatted(start)} – ${formatted(addDays(start, 6))}, ${start.getFullYear()}`
            : anchor.toLocaleDateString("en-US", {
                month: "long",
                year: "numeric",
              })}
        </strong>
        <Button
          onClick={() =>
            setAnchor((d) =>
              view === "Week"
                ? addDays(d, 7)
                : new Date(d.getFullYear(), d.getMonth() + 1, 1),
            )
          }
        >
          Next ›
        </Button>
        <Button onClick={() => setAnchor(today())}>Today</Button>
        <select
          aria-label="Calendar view"
          value={view}
          onChange={(e) => setView(e.target.value)}
        >
          <option value="Week">Week view</option>
          <option value="Month">Month view</option>
        </select>
      </div>
      {state.active.includes("history") && (
        <div className="card pathway">
          <h3>History learning pathway · Six months</h3>
          <div className="actions">
            <span className="pill green">Months 1–2 · History 7 ACTIVE</span>
            <span className="pill">Months 3–4 · History 8 PLANNED</span>
            <span className="pill amber">
              Months 5–6 · History 9 CONDITIONAL
            </span>
          </div>
        </div>
      )}
      <div className="calendar-scroll">
        <div className={`calendar ${view.toLowerCase()}`}>
          {calendarDays.map((d) => (
            <section
              key={dateKey(d)}
              className={`day ${dateKey(d) === dateKey(today()) ? "today" : ""} ${view === "Month" && d.getMonth() !== anchor.getMonth() ? "outside" : ""}`}
            >
              <h3>
                {d
                  .toLocaleDateString("en-US", { weekday: "short" })
                  .toUpperCase()}{" "}
                {d.getDate()}
              </h3>
              {state.sessions
                .filter((s) => s.date === dateKey(d))
                .sort((a, b) => a.time.localeCompare(b.time))
                .map((s) => (
                  <button
                    className={`calendar-event ${s.kind === "quiz" ? "amber" : courseFor(s.courseId).color}`}
                    key={s.id}
                    onClick={() => openLesson(s)}
                  >
                    <small>
                      {s.time} · {s.minutes}m
                    </small>
                    <strong>{s.title}</strong>
                    <small>{courseFor(s.courseId).name}</small>
                    {s.status !== "planned" && (
                      <small>
                        {s.status === "verified"
                          ? "✓ Verified"
                          : "Awaiting check"}
                      </small>
                    )}
                  </button>
                ))}
            </section>
          ))}
        </div>
      </div>
      <h2 className="section-title">Upcoming checkpoints</h2>
      <div className="card checkpoint">
        <span>{formatted(addDays(start, 6))} • Weekly revision</span>
        <span className="pill">Estimated: 45 min</span>
      </div>
    </>
  );
}
