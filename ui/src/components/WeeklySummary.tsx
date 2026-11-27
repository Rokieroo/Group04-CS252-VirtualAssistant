import type { Goal, Report } from "../api";
export function WeeklySummary({
  report,
  goals,
  onGoal,
  onAvailability,
  onReminder,
}: {
  report: Report;
  goals: Goal[];
  onGoal: (id: string, title: string, form: HTMLFormElement) => void;
  onAvailability: () => void;
  onReminder: (enabled: boolean) => void;
}) {
  return (
    <section
      className="card core-panel weekly-summary"
      aria-labelledby="weekly-summary"
    >
      <h2 id="weekly-summary">Weekly summary</h2>
      <p>
        {report.start_date} – {report.end_date}
      </p>
      {report.reminder_due && (
        <p role="status">You can review your study week whenever it suits you.</p>
      )}
      {!report.total_tasks &&
        !report.planned_minutes &&
        !report.review_count && (
          <p>No study activity recorded this week yet.</p>
        )}
      <p>
        {report.completed_nodes ?? 0} stages completed ·{" "}
        {report.overdue_nodes ?? 0} stages overdue · {report.review_count ?? 0}{" "}
        reviews.
      </p>
      <p>
        Study time logged: {report.completed_minutes} / {report.planned_minutes}{" "}
        planned minutes.
      </p>
      {(
        [
          ["Milestones in the next 7 days", report.upcoming_milestones],
          ["Stages needing review", report.review_nodes],
        ] as const
      ).map(([label, nodes]) => (
        <div key={label}>
          <h3>{label}</h3>
          {nodes?.length ? (
            <ul>
              {nodes.map((n) => (
                <li key={n.id}>
                  <a
                    href={`?${new URLSearchParams({ kg_roadmap: n.roadmap_id, kg_node: n.id })}#roadmap`}
                  >
                    {n.title}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p>No stages yet.</p>
          )}
        </div>
      ))}
      {report.next_week_deadline && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const values = new FormData(form);
            onGoal(
              String(values.get("goal_id") || ""),
              String(values.get("title") || "").trim(),
              form,
            );
          }}
        >
          <label>
            Next week's goal
            <select
              name="goal_id"
              onChange={(event) => {
                const input =
                  event.currentTarget.form?.elements.namedItem("title");
                if (input instanceof HTMLInputElement)
                  input.value =
                    goals.find((g) => g.id === event.currentTarget.value)
                      ?.title ?? "";
              }}
            >
              <option value="">Add a goal</option>
              {goals
                .filter(
                  (g) =>
                    g.due_at &&
                    Date.parse(g.due_at) <=
                      Date.parse(report.next_week_deadline!) &&
                    Date.parse(g.due_at) >
                      Date.parse(report.next_week_deadline!) -
                        7 * 24 * 60 * 60 * 1000,
                )
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Goal name
            <input name="title" required maxLength={200} />
          </label>
          <button>Save goal</button>
        </form>
      )}
      <button onClick={onAvailability}>Adjust availability</button>
      <button
        aria-pressed={!!report.reminder_enabled}
        onClick={() => onReminder(!report.reminder_enabled)}
      >
        {report.reminder_enabled ? "Turn off" : "Turn on"} Sunday 7:00 PM
        summary reminder
      </button>
    </section>
  );
}
