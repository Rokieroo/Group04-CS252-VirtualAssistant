import { Button } from "../components/Button";
import { Meter } from "../components/ProgressMeter";
import { courseFor } from "../demo/selectors";
import type { Session, State } from "../domain";
import { completion, pendingCount, verifiedCount } from "../model";

type Props = {
  state: State;
  courseId: string;
  setCourseId: (id: string) => void;
  openLesson: (session: Session) => void;
};
export function ProgressPage({
  state,
  courseId,
  setCourseId,
  openLesson,
}: Props) {
  const summary = completion(state, courseId);
  const courseSessions = state.sessions
    .filter((session) => session.courseId === courseId)
    .sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));
  return (
    <>
      <div className="toolbar">
        <label>
          Learning goal{" "}
          <select
            aria-label="Learning goal"
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
          >
            {state.active.map((id) => (
              <option key={id} value={id}>
                {courseFor(id).name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="two-columns">
        <section className="card progress-summary">
          <h3>Verified course completion</h3>
          <strong className="big-number">{summary.percent}%</strong>
          <Meter value={summary.percent} />
          <p>
            {summary.verified} / {summary.total}{" "}
            {courseId === "english" ? "demo lessons" : "sample sessions"}{" "}
            verified
          </p>
          {summary.baseline > 0 && (
            <p className="footnote">
              Includes {summary.baseline} example lessons completed before this
              demo. Listed sessions begin unverified.
            </p>
          )}
        </section>
        <section className="card progress-summary">
          <h3>Assessment summary</h3>
          <div className="stats">
            <div>
              <strong>{pendingCount(state, courseId)}</strong>
              <p>Pending checks</p>
            </div>
            <div>
              <strong>{verifiedCount(state, courseId)}</strong>
              <p>Checks passed this demo</p>
            </div>
          </div>
          <hr />
          <p>Listed sessions become verified only after a passing check.</p>
        </section>
      </div>
      <h2 className="section-title">Scheduled sessions</h2>
      {courseSessions.length === 0 && (
        <p className="card empty">
          No sessions are scheduled for this course yet.
        </p>
      )}
      {courseSessions.map((session, i) => {
        const verified = state.verified.includes(session.id);
        const status = verified
          ? "Verified"
          : session.status === "studied"
            ? "Awaiting check"
            : "Planned";
        return (
          <article className="card milestone" key={session.id}>
            <span className={`number ${verified ? "green" : ""}`}>
              {String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <h3>{session.title}</h3>
              <p>
                {status} · {session.date} · {session.time}
              </p>
            </div>
            <Button onClick={() => openLesson(session)}>
              {session.kind === "quiz"
                ? verified
                  ? "Retake check"
                  : "Take check"
                : "Open lesson"}
            </Button>
          </article>
        );
      })}
      <p className="footnote">These cards show scheduled demo sessions.</p>
    </>
  );
}
