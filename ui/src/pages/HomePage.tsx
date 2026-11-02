import { Button } from "../components/Button";
import { Meter } from "../components/ProgressMeter";
import { courseFor } from "../demo/selectors";
import type { Session, State } from "../domain";
import { completion, pendingCount, verifiedCount } from "../model";
import { pageLabels, type Page } from "../navigation";
import { dateKey, today } from "../time";

type Props = {
  state: State;
  go: (page: Page) => void;
  openLesson: (session: Session) => void;
};
export function HomePage({ state, go, openLesson }: Props) {
  const todays = state.sessions.filter((s) => s.date === dateKey(today()));
  const plannedToday = todays.filter((s) => s.status === "planned").length;
  const english = completion(state, "english");
  return (
    <>
      <section className="card hero">
        <div className="ai-symbol">✦</div>
        <div>
          <h2>What would you like to learn?</h2>
          <p>Create a new learning goal or adjust your current roadmap.</p>
        </div>
        <Button primary onClick={() => go("AI Reporter")}>
          Plan in {pageLabels["AI Reporter"]} →
        </Button>
      </section>
      <h2 className="section-title">Today's focus</h2>
      <p className="section-caption">
        {today().toLocaleDateString("en-US", { weekday: "long" })} •{" "}
        {todays.length} sessions · {plannedToday} planned
      </p>
      <div className="home-grid">
        <div className="session-list">
          {todays.map((s) => (
            <article
              className={`card session ${s.kind === "quiz" ? "amber" : "purple"}`}
              key={s.id}
            >
              <div className="session-content">
                <span className="pill">
                  {s.time} · {s.minutes} min
                </span>
                <h3>{s.title}</h3>
                <p>
                  {s.kind === "quiz"
                    ? "Knowledge check · Verification required"
                    : `${courseFor(s.courseId).name} · Sample lesson`}
                </p>
              </div>
              <Button onClick={() => openLesson(s)}>
                {s.kind === "quiz"
                  ? s.status === "verified"
                    ? "Retake quiz"
                    : "Take quiz"
                  : s.status === "verified"
                    ? "Open lesson"
                    : "Start lesson"}
              </Button>
            </article>
          ))}
        </div>
        <section className="card overview">
          <h3>Goal overview</h3>
          <div className="metric-line">
            <strong>{english.percent}%</strong>
            <span>Verified progress</span>
          </div>
          <Meter value={english.percent} />
          <hr />
          <b>
            {english.verified} of {english.total} demo lessons verified
          </b>
          <p className="amber-text">
            {pendingCount(state, "english")} lessons awaiting assessment
          </p>
        </section>
      </div>
      <section className="card insight">
        <span className="ai-symbol green">✧</span>
        <div>
          <h3>Study suggestion</h3>
          <p>
            {verifiedCount(state, "english") > 0
              ? "Your latest verified check is recorded. Review difficult topics before moving on."
              : "Complete a knowledge check to verify progress and unlock a more specific recommendation."}
          </p>
        </div>
      </section>
    </>
  );
}
