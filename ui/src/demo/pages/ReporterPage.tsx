// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { type RefObject } from "react";
import { Button } from "../../components/Button";
import { Meter } from "../../components/ProgressMeter";
import { courseFor } from "../selectors";
import type { State } from "../domain";
import { formatted } from "../../format";
import type { Proposal } from "../domain";
import { dateKey, today } from "../../time";

type Props = {
  state: State;
  gradeChoice: boolean;
  proposal: Proposal | null;
  setProposal: (proposal: Proposal | null) => void;
  requestCourse: (id: string) => void;
  say: (text: string) => void;
  defer: () => void;
  approve: () => void;
  adjust: () => void;
  send: (text?: string) => void;
  chat: string;
  setChat: (text: string) => void;
  chatEnd: RefObject<HTMLDivElement | null>;
  onReport: () => void;
  onFuturePlan: () => void;
};
export function ReporterPage({
  state,
  gradeChoice,
  proposal,
  setProposal,
  requestCourse,
  say,
  defer,
  approve,
  adjust,
  send,
  chat,
  setChat,
  chatEnd,
  onReport,
  onFuturePlan,
}: Props) {
  const pendingCourse = proposal?.courseId
    ? courseFor(proposal.courseId)
    : null;
  const overloaded =
    proposal?.kind === "enroll" &&
    state.active.length * 3 + (proposal?.hours || 0) > state.hours;

  const todays = state.sessions.filter((s) => s.date === dateKey(today()));
  return (
    <div className="chat-layout">
      <section className="card chat-panel">
        <div className="chat-heading">
          <h3>✦ Pathly AI</h3>
          <span className="pill green">Simulated learning coach</span>
        </div>
        <div className="chat-history" role="log" aria-live="polite">
          {state.messages.map((m, i) => (
            <div key={i} className={`message ${m.role}`}>
              {m.role === "assistant" && <b>✦ Pathly AI</b>}
              <p>{m.text}</p>
            </div>
          ))}
          {gradeChoice && (
            <div className="message assistant">
              <h3>Choose your Physics level</h3>
              <div className="actions">
                <Button onClick={() => requestCourse("physics")}>
                  Grade 7 · Beginner
                </Button>
                <Button onClick={() => requestCourse("physics12")}>
                  Grade 12 · Advanced
                </Button>
              </div>
            </div>
          )}
          {proposal && (
            <div className="proposal">
              <h3>
                {proposal.kind === "balance"
                  ? "Review workload adjustment"
                  : `${pendingCourse!.name} · ${proposal.stage === "check" ? "Starting point" : "Proposed plan"}`}
              </h3>
              {proposal.kind === "enroll" && proposal.stage === "check" ? (
                <>
                  <p>Prerequisite: {pendingCourse!.prerequisite}.</p>
                  <p>
                    {pendingCourse!.id === "history"
                      ? "Start with History 7. History 8 and 9 remain conditional until earlier assessments are passed."
                      : "This demo uses your confirmation; a real prerequisite assessment will be connected later."}
                  </p>
                  <div className="actions">
                    <Button
                      primary
                      onClick={() =>
                        setProposal({ ...proposal, stage: "review" })
                      }
                    >
                      {pendingCourse!.id === "history"
                        ? "Start with History 7"
                        : "I meet the prerequisite"}
                    </Button>
                    <Button
                      onClick={() => {
                        if (pendingCourse!.id === "physics12")
                          requestCourse("physics");
                        else
                          say(
                            "Start with the foundation material or save this module for later. Enrollment has not changed.",
                          );
                      }}
                    >
                      I need foundations
                    </Button>
                    <Button onClick={defer}>Add to future plan</Button>
                  </div>
                </>
              ) : (
                <>
                  <label className="field">
                    {proposal.kind === "balance"
                      ? "Weekly study budget"
                      : "Hours per week for this course"}
                    <input
                      type="number"
                      min="1"
                      max="40"
                      value={proposal.hours}
                      onChange={(e) =>
                        setProposal({
                          ...proposal,
                          hours: Math.max(
                            1,
                            Math.min(40, Number(e.target.value) || 1),
                          ),
                        })
                      }
                    />
                  </label>
                  {proposal.kind === "balance" ? (
                    <>
                      <p>
                        Your{" "}
                        {
                          state.sessions.filter((s) => s.status === "planned")
                            .length
                        }{" "}
                        planned sessions will be resized to fit this budget
                        (10–60 minutes each). Completed work stays verified.
                      </p>
                      <div className="balance-bars">
                        {state.active.map((id) => (
                          <div key={id}>
                            <span>{courseFor(id).name}</span>
                            <Meter value={100 / state.active.length} />
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <>
                      <p>
                        {pendingCourse!.weeks} weeks · 3 sample sessions to
                        preview your first topics.
                      </p>
                      <ul>
                        {pendingCourse!.topics.map((t) => (
                          <li key={t}>{t}</li>
                        ))}
                      </ul>
                      {pendingCourse!.id === "history" && (
                        <p>
                          Months 1–2: History 7 · Months 3–4: History 8
                          (planned) · Months 5–6: History 9 (conditional).
                        </p>
                      )}
                      {overloaded && (
                        <div className="warning">
                          <b>This may overload your schedule.</b>
                          <p>
                            Your {state.active.length} active goals have an
                            estimated {state.active.length * 3}h weekly
                            workload. This request adds {proposal.hours}h to
                            your {state.hours}h budget. Save it for later or
                            review your workload.
                          </p>
                        </div>
                      )}
                    </>
                  )}
                  <div className="actions">
                    <Button primary onClick={approve} disabled={overloaded}>
                      Approve {proposal.kind === "balance" ? "changes" : "plan"}
                    </Button>
                    {proposal.kind === "enroll" && (
                      <Button onClick={defer}>Add to future plan</Button>
                    )}
                    {overloaded && (
                      <Button onClick={adjust}>Review workload</Button>
                    )}
                    <Button
                      onClick={() => {
                        setProposal(null);
                        say("Proposal dismissed. Your schedule is unchanged.");
                      }}
                    >
                      Not now
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
          {!proposal && !gradeChoice && (
            <div className="suggestions">
              {[
                "Learn Math 7",
                "Learn Physics",
                "Learn History 9",
                "Learn Biology 9",
              ].map((s) => (
                <Button key={s} onClick={() => send(s)}>
                  {s}
                </Button>
              ))}
            </div>
          )}
          <div ref={chatEnd} />
        </div>
        <form
          className="chat-input"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            aria-label="Message Pathly AI"
            placeholder="Ask anything or tell me what to adjust..."
            value={chat}
            onChange={(e) => setChat(e.target.value)}
          />
          <button aria-label="Send message" disabled={!chat.trim()}>
            ➤
          </button>
        </form>
      </section>
      <aside className="card report-panel">
        <h3>Daily report</h3>
        <span className="pill">{formatted(today())}</span>
        <hr />
        <h4>Today's status</h4>
        <p>
          {todays.filter((s) => s.status !== "planned").length} /{" "}
          {todays.length} sessions studied
        </p>
        <Meter
          value={
            todays.length
              ? (todays.filter((s) => s.status !== "planned").length /
                  todays.length) *
                100
              : 0
          }
        />
        <h4>AI observations</h4>
        <p>
          • Steady study routine
          <br />• Past tenses need practice
          <br />• Assessments verify progress
        </p>
        <hr />
        <h4>Suggested actions</h4>
        <Button onClick={adjust}>Adjust workload</Button>
        <Button onClick={onReport}>Generate weekly report</Button>
        <Button onClick={onFuturePlan}>
          View future plan ({state.future.length})
        </Button>
        <h4>Active learning goals</h4>
        {state.active.map((id) => (
          <p key={id}>{courseFor(id).name}</p>
        ))}
        <p className="footnote">
          Plan changes require your confirmation. Responses are scripted; no AI
          service is connected.
        </p>
      </aside>
    </div>
  );
}
