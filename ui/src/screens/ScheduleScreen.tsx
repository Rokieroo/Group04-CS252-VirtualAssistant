import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { BusyBlock, Entry, Plan, PlanRequest, Report, Task, Window as FreeWindow } from "../api";
import { call } from "../api/backend";
import { dateTimeLabel, dayLabel, duration, explain, localAfter, timeLabel } from "../app/text";
import type { Course } from "../app/useCourse";
import { Button, Chip, Dialog, Empty, Field, IconButton, Loading, Notice, PageHead } from "../ui/kit";

type Session = { id: string; title: string; starts_at: string; ends_at?: string; status?: string };
type Data = { tasks: Task[]; windows: FreeWindow[]; blocks: BusyBlock[]; entries: Entry[]; report: Report };

const WEEK_MS = 7 * 24 * 60 * 60_000;
const iso = (form: FormData, key: string) => new Date(String(form.get(key))).toISOString();
const post = (path: string, body: unknown, method = "POST") =>
  call(path, { method, body: JSON.stringify(body) });

/** Sessions under a heading per day, soonest first. */
function byDay(sessions: Session[]) {
  const days = new Map<string, Session[]>();
  for (const s of [...sessions].sort((a, b) => a.starts_at.localeCompare(b.starts_at))) {
    const key = new Date(s.starts_at).toDateString();
    days.set(key, [...(days.get(key) ?? []), s]);
  }
  return [...days.values()];
}

/** How much study time the roadmap may take; the first step of scheduling in both modes. */
function BudgetForm({ course, onDone }: { course: Course; onDone?: () => void }) {
  const [daily, setDaily] = useState(120);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (await course.schedule(course.weekly, daily)) onDone?.();
  };
  return (
    <form className="budget" onSubmit={submit}>
      <div className="form-grid">
        <Field label="Thời gian học mỗi tuần (phút)" hint={duration(course.weekly)}>
          <input
            type="number"
            min={30}
            max={3000}
            step={30}
            required
            value={course.weekly}
            onChange={(event) => course.setWeekly(Number(event.target.value))}
          />
        </Field>
        <Field label="Nhiều nhất mỗi ngày (phút)" hint={duration(daily)}>
          <input
            type="number"
            min={15}
            max={720}
            step={15}
            required
            value={daily}
            onChange={(event) => setDaily(Number(event.target.value))}
          />
        </Field>
      </div>
      <div className="row">
        <Button type="submit" variant="primary" disabled={course.busy}>
          {course.busy ? "Đang xếp lịch…" : "Xếp lộ trình vào lịch"}
        </Button>
        {course.mock && (
          <span className="muted small grow">
            Bản xem thử xếp mỗi bước vào một buổi tối. Ứng dụng đầy đủ xếp theo giờ rảnh thật của bạn.
          </span>
        )}
      </div>
      {course.error && <Notice tone="error">{course.error}</Notice>}
    </form>
  );
}

/** Preview a new plan for the unfinished work, then save it: nothing changes before "Lưu". */
function ReplanDialog({
  tasks,
  onClose,
  onSaved,
}: {
  tasks: Task[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [preview, setPreview] = useState<{ request: PlanRequest; plan: Plan } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const title = (id: string) => tasks.find((t) => t.id === id)?.title ?? "Nhiệm vụ đã lưu trữ";
  // The plan never starts in the past: checked-in sessions stay, the rest moves forward.
  const fromNow = (start: string) => new Date(Math.max(Date.parse(start), Date.now())).toISOString();

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };
  const propose = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const request: PlanRequest = {
      starts_at: fromNow(iso(form, "start")),
      ends_at: iso(form, "end"),
      max_session_minutes: Number(form.get("session")),
      daily_limit_minutes: Number(form.get("daily")),
    };
    void run(async () =>
      setPreview({ request, plan: (await post("/schedule/replan", request)) as Plan }),
    );
  };
  const save = () =>
    run(async () => {
      await post("/schedule/replan", {
        ...preview!.request,
        starts_at: fromNow(preview!.request.starts_at),
        commit: true,
      });
      onSaved();
    });

  return (
    <Dialog
      wide
      title="Xếp lại lịch"
      onClose={onClose}
      footer={
        preview ? (
          <>
            <Button disabled={busy} onClick={() => setPreview(null)}>
              Chỉnh lại
            </Button>
            <Button variant="primary" disabled={busy} onClick={() => void save()}>
              Lưu lịch này
            </Button>
          </>
        ) : (
          <Button type="submit" form="replan" variant="primary" disabled={busy}>
            {busy ? "Đang tính…" : "Xem lịch đề xuất"}
          </Button>
        )
      }
    >
      {error && <Notice tone="error">{error}</Notice>}
      {!preview ? (
        <form id="replan" className="stack" onSubmit={propose}>
          <p className="muted">
            Các buổi đã điểm danh được giữ nguyên. Những buổi chưa học được xếp lại vào giờ rảnh của bạn.
          </p>
          <div className="form-grid">
            <Field label="Xếp từ">
              <input name="start" type="datetime-local" defaultValue={localAfter(1)} required />
            </Field>
            <Field label="Đến">
              <input name="end" type="datetime-local" defaultValue={localAfter(7 * 1440)} required />
            </Field>
            <Field label="Mỗi buổi dài nhất (phút)">
              <input name="session" type="number" defaultValue={60} min={15} max={240} required />
            </Field>
            <Field label="Mỗi ngày nhiều nhất (phút)">
              <input name="daily" type="number" defaultValue={180} min={1} max={1440} required />
            </Field>
          </div>
        </form>
      ) : (
        <div className="stack">
          {preview.plan.expired_sessions > 0 && (
            <Notice tone="warn">
              Lưu lịch này sẽ đánh dấu {preview.plan.expired_sessions} buổi đã qua mà chưa điểm danh là bỏ
              lỡ. Nếu bạn đã học, hãy điểm danh trước.
            </Notice>
          )}
          <h3>{preview.plan.entries.length} buổi học mới</h3>
          {preview.plan.entries.length === 0 && (
            <p className="muted">Không buổi nào xếp vừa. Thêm giờ rảnh hoặc nới khoảng thời gian.</p>
          )}
          <ul className="plain-list">
            {preview.plan.entries.map((entry, i) => (
              <li key={i}>
                <strong>{title(entry.task_id)}</strong>
                <span className="muted small">
                  {dateTimeLabel(entry.starts_at)} đến {timeLabel(entry.ends_at)}
                </span>
              </li>
            ))}
          </ul>
          {preview.plan.unscheduled.map((item) => (
            <Notice tone="warn" key={item.task_id}>
              {title(item.task_id)}: còn {duration(item.minutes)} chưa xếp được (
              {item.reason.replaceAll("_", " ")}).
            </Notice>
          ))}
        </div>
      )}
    </Dialog>
  );
}

/** A list the learner adds to and removes from: free time or busy time. */
function TimeList({
  title,
  hint,
  items,
  withTitle,
  disabled,
  onAdd,
  onRemove,
}: {
  title: string;
  hint: string;
  items: (FreeWindow & { title?: string })[];
  withTitle?: boolean;
  disabled: boolean;
  onAdd: (form: FormData) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <details className="fold">
      <summary>
        {title} ({items.length})
      </summary>
      <div className="fold-body stack">
        <p className="muted small">{hint}</p>
        <ul className="plain-list">
          {items.map((item) => (
            <li key={item.id}>
              <span className="grow">
                {item.title && <strong>{item.title} </strong>}
                {dateTimeLabel(item.starts_at)} đến {timeLabel(item.ends_at)}
              </span>
              <IconButton
                icon="trash"
                label={`Xóa ${item.title ?? "giờ rảnh"} ${dateTimeLabel(item.starts_at)}`}
                disabled={disabled}
                onClick={() => onRemove(item.id)}
              />
            </li>
          ))}
        </ul>
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            onAdd(new FormData(event.currentTarget));
          }}
        >
          {withTitle && (
            <Field label="Việc bận">
              <input name="title" defaultValue="Lên lớp" required maxLength={200} />
            </Field>
          )}
          <Field label="Từ">
            <input name="start" type="datetime-local" defaultValue={localAfter(60)} required />
          </Field>
          <Field label="Đến">
            <input name="end" type="datetime-local" defaultValue={localAfter(180)} required />
          </Field>
          <Button type="submit" icon="plus" disabled={disabled}>
            Thêm
          </Button>
        </form>
      </div>
    </details>
  );
}

function Agenda({
  sessions,
  disabled,
  onCheckIn,
}: {
  sessions: Session[];
  disabled?: boolean;
  onCheckIn?: (id: string, body: { status: string; actual_minutes?: number }) => void;
}) {
  return (
    <div className="agenda">
      {byDay(sessions).map((day) => (
        <section key={day[0].id} className="agenda-day">
          <h3>{dayLabel(day[0].starts_at)}</h3>
          <ul>
            {day.map((s) => {
              const minutes = s.ends_at ? (Date.parse(s.ends_at) - Date.parse(s.starts_at)) / 60_000 : 0;
              const started = Date.now() >= Date.parse(s.starts_at);
              return (
                <li key={s.id} className={`session session-${s.status ?? "planned"}`}>
                  <span className="session-time">
                    {timeLabel(s.starts_at)}
                    {s.ends_at && <span className="muted"> đến {timeLabel(s.ends_at)}</span>}
                  </span>
                  <strong className="grow">{s.title}</strong>
                  {s.status === "completed" && <Chip tone="route">Đã học</Chip>}
                  {s.status === "missed" && <Chip tone="danger">Bỏ lỡ</Chip>}
                  {s.status === "planned" && !started && <Chip>Sắp tới</Chip>}
                  {s.status === "planned" && started && onCheckIn && (
                    <form
                      className="row"
                      onSubmit={(event) => {
                        event.preventDefault();
                        onCheckIn(s.id, {
                          status: "completed",
                          actual_minutes: Number(new FormData(event.currentTarget).get("minutes")),
                        });
                      }}
                    >
                      <input
                        className="minutes"
                        name="minutes"
                        type="number"
                        aria-label={`Số phút đã học: ${s.title}`}
                        min={1}
                        max={minutes}
                        defaultValue={minutes}
                        required
                      />
                      <Button type="submit" size="sm" variant="primary" disabled={disabled}>
                        Đã học
                      </Button>
                      <Button
                        size="sm"
                        variant="quiet"
                        disabled={disabled}
                        onClick={() => onCheckIn(s.id, { status: "missed" })}
                      >
                        Bỏ lỡ
                      </Button>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** The calendar on the server: check in, keep free and busy time current, and replan. */
function LiveSchedule({ course }: { course: Course }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [replanning, setReplanning] = useState(false);

  const load = useCallback(async () => {
    const [tasks, windows, blocks, entries, report] = await Promise.all([
      call<Task[]>("/tasks?limit=500"),
      call<FreeWindow[]>("/availability"),
      call<BusyBlock[]>("/busy-blocks"),
      call<Entry[]>("/schedule"),
      call<Report>("/reports/weekly"),
    ]);
    setData({ tasks, windows, blocks, entries, report });
  }, []);
  const run = useCallback(
    async (work?: () => Promise<unknown>) => {
      setBusy(true);
      setError("");
      try {
        await work?.();
        await load();
      } catch (e) {
        setError(explain(e));
      } finally {
        setBusy(false);
      }
    },
    [load],
  );
  useEffect(() => void run(), [run]);

  if (!data)
    return error ? (
      <Notice tone="error" action={<Button onClick={() => void run()}>Thử lại</Button>}>
        {error}
      </Notice>
    ) : (
      <Loading>Đang tải lịch học…</Loading>
    );

  const { tasks, windows, blocks, report } = data;
  const slots = (list: FreeWindow[]) => list.map(({ starts_at, ends_at }) => ({ starts_at, ends_at }));
  // Past sessions that still need a check-in stay; the rest of the past fades after a week.
  const sessions: Session[] = data.entries
    .filter((e) => e.status === "planned" || Date.parse(e.ends_at) > Date.now() - WEEK_MS)
    .map((e) => ({ ...e, title: tasks.find((t) => t.id === e.task_id)?.title ?? "Nhiệm vụ đã lưu trữ" }));

  return (
    <>
      {error && <Notice tone="error">{error}</Notice>}
      {course.plan?.unscheduled?.length ? (
        <Notice tone="warn" title={`${course.plan.unscheduled.length} bước chưa xếp được vào lịch`}>
          Thêm giờ rảnh rồi xếp lại lịch.
        </Notice>
      ) : null}

      <dl className="figures" aria-label="Tuần này">
        <div>
          <dt>Nhiệm vụ xong tuần này</dt>
          <dd>
            {report.completed_tasks}/{report.total_tasks}
          </dd>
        </div>
        <div>
          <dt>Đã học</dt>
          <dd>{duration(report.completed_minutes) || "0 phút"}</dd>
        </div>
        <div>
          <dt>Buổi bỏ lỡ</dt>
          <dd>{report.missed_sessions}</dd>
        </div>
      </dl>

      <div className="schedule">
        <section className="section" aria-labelledby="agenda-title">
          <div className="section-head">
            <h2 id="agenda-title">Các buổi học</h2>
            {sessions.length > 0 && (
              <Button icon="refresh" disabled={busy} onClick={() => setReplanning(true)}>
                Xếp lại lịch
              </Button>
            )}
          </div>
          {sessions.length > 0 ? (
            <Agenda
              sessions={sessions}
              disabled={busy}
              onCheckIn={(id, body) => void run(() => post(`/schedule/${id}/check-in`, body))}
            />
          ) : course.stage === "ready" ? (
            <>
              <p className="muted">
                Chưa có buổi học nào. Thêm giờ rảnh ở bên cạnh, rồi cho biết bạn học được bao nhiêu.
              </p>
              <BudgetForm course={course} onDone={() => void run()} />
            </>
          ) : (
            <Empty
              icon="schedule"
              title="Chưa có gì để xếp lịch"
              action={
                <a className="btn btn-primary btn-md" href="#course">
                  Tới mục Môn học
                </a>
              }
            >
              Duyệt lộ trình trước, rồi các bước học sẽ được xếp vào giờ rảnh của bạn.
            </Empty>
          )}
        </section>

        <section className="section" aria-labelledby="time-title">
          <h2 id="time-title">Thời gian của bạn</h2>
          <TimeList
            title="Giờ rảnh"
            hint="Buổi học chỉ được xếp vào giờ rảnh. Thay đổi giờ rảnh sẽ xóa các buổi sắp tới chưa điểm danh, hãy xếp lại lịch sau đó."
            items={windows}
            disabled={busy}
            onAdd={(form) =>
              void run(() =>
                post(
                  "/availability",
                  { windows: [...slots(windows), { starts_at: iso(form, "start"), ends_at: iso(form, "end") }] },
                  "PUT",
                ),
              )
            }
            onRemove={(id) =>
              void run(() => post("/availability", { windows: slots(windows.filter((w) => w.id !== id)) }, "PUT"))
            }
          />
          <TimeList
            title="Giờ bận"
            hint="Lên lớp, đi làm, việc riêng. Buổi học trùng giờ bận sẽ bị xóa để bạn xếp lại."
            items={blocks}
            withTitle
            disabled={busy}
            onAdd={(form) =>
              void run(() =>
                post("/busy-blocks", {
                  title: String(form.get("title")),
                  starts_at: iso(form, "start"),
                  ends_at: iso(form, "end"),
                }),
              )
            }
            onRemove={(id) => void run(() => call(`/busy-blocks/${id}`, { method: "DELETE" }))}
          />
        </section>
      </div>

      {replanning && (
        <ReplanDialog
          tasks={tasks}
          onClose={() => setReplanning(false)}
          onSaved={() => {
            setReplanning(false);
            void run();
          }}
        />
      )}
    </>
  );
}

/** The preview has no calendar: it shows the sessions the roadmap would become. */
function PreviewSchedule({ course }: { course: Course }) {
  if (course.stage !== "ready")
    return (
      <Empty
        icon="schedule"
        title="Chưa có gì để xếp lịch"
        action={
          <a className="btn btn-primary btn-md" href="#course">
            Tới mục Môn học
          </a>
        }
      >
        Duyệt lộ trình trước, rồi các bước học sẽ được xếp thành từng buổi.
      </Empty>
    );
  return (
    <div className="stack">
      <BudgetForm course={course} />
      {course.plan && (
        <section className="section" aria-labelledby="agenda-title">
          <h2 id="agenda-title">{course.plan.sessions.length} buổi học</h2>
          <Agenda sessions={course.plan.sessions} />
        </section>
      )}
    </div>
  );
}

export function ScheduleScreen({ course }: { course: Course }) {
  return (
    <>
      <PageHead
        title="Lịch học"
        lead="Mỗi bước của lộ trình thành một buổi học trong giờ rảnh của bạn. Học xong thì điểm danh."
      />
      {course.mock ? <PreviewSchedule course={course} /> : <LiveSchedule course={course} />}
    </>
  );
}
