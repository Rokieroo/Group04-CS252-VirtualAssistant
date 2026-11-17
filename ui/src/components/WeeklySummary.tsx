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
      <h2 id="weekly-summary">Tổng kết tuần</h2>
      <p>
        {report.start_date} – {report.end_date}
      </p>
      {report.reminder_due && (
        <p role="status">Bạn có thể xem lại tuần học khi thuận tiện.</p>
      )}
      {!report.total_tasks &&
        !report.planned_minutes &&
        !report.review_count && (
          <p>Tuần này chưa có hoạt động học được ghi nhận.</p>
        )}
      <p>
        {report.completed_nodes ?? 0} chặng hoàn thành ·{" "}
        {report.overdue_nodes ?? 0} chặng quá hạn · {report.review_count ?? 0}{" "}
        lượt ôn.
      </p>
      <p>
        Thời gian đã học: {report.completed_minutes} / {report.planned_minutes}{" "}
        phút theo kế hoạch.
      </p>
      {(
        [
          ["Mốc trong 7 ngày tới", report.upcoming_milestones],
          ["Chặng cần ôn", report.review_nodes],
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
            <p>Chưa có chặng.</p>
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
            Mục tiêu tuần sau
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
              <option value="">Thêm mục tiêu</option>
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
            Tên mục tiêu
            <input name="title" required maxLength={200} />
          </label>
          <button>Lưu mục tiêu</button>
        </form>
      )}
      <button onClick={onAvailability}>Chỉnh giờ rảnh</button>
      <button
        aria-pressed={!!report.reminder_enabled}
        onClick={() => onReminder(!report.reminder_enabled)}
      >
        {report.reminder_enabled ? "Tắt" : "Bật"} nhắc tổng kết Chủ nhật lúc 19
        giờ
      </button>
    </section>
  );
}
