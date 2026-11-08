import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiClient, type Auth, type BusyBlock, type ChatReply, type Entry, type Goal, type Invitation,
  type Member, type Message, type Notification, type Plan, type PlanRequest, type Report,
  type Task, type Team, type User, type Window as FreeWindow,
} from "./api";
import "./workspace.css";

type Snapshot = {
  user: User; tasks: Task[]; goals: Goal[]; windows: FreeWindow[]; blocks: BusyBlock[];
  entries: Entry[]; teams: Team[]; invitations: Invitation[]; notifications: Notification[];
  report: Report; messages: Message[];
};
const text = (form: FormData, key: string) => String(form.get(key) || "");
const number = (form: FormData, key: string) => Number(form.get(key));
const iso = (form: FormData, key: string) => new Date(text(form, key)).toISOString();
const localAfter = (minutes: number) => {
  const date = new Date(Date.now() + minutes * 60_000);
  date.setSeconds(0, 0);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
const storedToken = () => {
  try { return sessionStorage.getItem("pathly.session") || ""; } catch { return ""; }
};

export default function Workspace() {
  const [token, setToken] = useState(storedToken);
  const activeToken = useRef(token);
  activeToken.current = token;
  const [data, setData] = useState<Snapshot | null>(null);
  const [registering, setRegistering] = useState(false);
  const [tab, setTab] = useState("Planner");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [preview, setPreview] = useState<{ request: PlanRequest; plan: Plan } | null>(null);
  const [teamId, setTeamId] = useState("");
  const selectedTeamId = useRef(teamId);
  selectedTeamId.current = teamId;
  const [members, setMembers] = useState<Member[]>([]);
  const [common, setCommon] = useState<{ starts_at: string; ends_at: string }[] | null>(null);
  const [aiStatus, setAiStatus] = useState("");
  const chatEnd = useRef<HTMLDivElement>(null);
  const expire = useCallback(() => {
    activeToken.current = "";
    setToken(""); setData(null); setPreview(null); setMembers([]); setTeamId("");
    try { sessionStorage.removeItem("pathly.session"); } catch { /* memory-only session */ }
  }, []);
  const api = useMemo(() => new ApiClient(token, expire), [token, expire]);
  const refresh = useCallback(async () => {
    if (!token) return;
    const [user, tasks, goals, windows, blocks, entries, teams, invitations, notifications, report, messages, loadedMembers] =
      await Promise.all([
        api.request<User>("/api/v1/me"), api.request<Task[]>("/api/v1/tasks?limit=500"),
        api.request<Goal[]>("/api/v1/goals"), api.request<FreeWindow[]>("/api/v1/availability"),
        api.request<BusyBlock[]>("/api/v1/busy-blocks"), api.request<Entry[]>("/api/v1/schedule"),
        api.request<Team[]>("/api/v1/teams"), api.request<Invitation[]>("/api/v1/invitations"),
        api.request<Notification[]>("/api/v1/notifications"), api.request<Report>("/api/v1/reports/weekly"),
        api.request<Message[]>("/api/v1/ai/messages"),
        teamId ? api.request<Member[]>(`/api/v1/teams/${teamId}/members`) : Promise.resolve([] as Member[]),
      ]);
    if (activeToken.current === token && selectedTeamId.current === teamId) {
      setData({ user, tasks, goals, windows, blocks, entries, teams, invitations, notifications, report, messages });
      setMembers(loadedMembers);
    }
  }, [api, token, teamId]);

  useEffect(() => {
    let active = true;
    if (token) {
      setPending(true);
      refresh().catch(e => { if (active) setError(e.message); })
        .finally(() => { if (active) setPending(false); });
    }
    return () => { active = false; };
  }, [refresh, token]);

  useEffect(() => {
    if (!token) return;
    const timer = setInterval(() => {
      api.request<Notification[]>("/api/v1/notifications").then(notifications => {
        if (activeToken.current === token) setData(current => current && { ...current, notifications });
      }).catch(() => { /* Foreground actions expose errors; polling resumes next time. */ });
    }, 30_000);
    return () => clearInterval(timer);
  }, [api, token]);

  useEffect(() => {
    setMembers([]); setCommon(null);
  }, [teamId]);

  useEffect(() => { chatEnd.current?.scrollIntoView({ block: "nearest" }); }, [data?.messages.length]);

  const run = async (action: () => Promise<unknown>, message = "Saved.", keepPreview = false) => {
    setPending(true); setError(""); setStatus("");
    if (!keepPreview) setPreview(null);
    setCommon(null);
    try {
      await action();
      if (token && activeToken.current === token) await refresh();
      setStatus(message);
    } catch (e) { setError(e instanceof Error ? e.message : "The request failed."); }
    finally { setPending(false); }
  };
  const submit = (event: FormEvent<HTMLFormElement>, action: (values: FormData, form: HTMLFormElement) => Promise<unknown>, message?: string) => {
    event.preventDefault();
    const form = event.currentTarget;
    void run(() => action(new FormData(form), form), message);
  };
  const format = (value: string) => new Date(value).toLocaleString(undefined, {
    timeZone: data?.user.timezone, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
  const taskName = (id: string) => data?.tasks.find(task => task.id === id)?.title || "Archived task";
  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return <div className="live-workspace">
    {error && <div role="alert" className="workspace-error">{error}</div>}
    {status && <div role="status" className="workspace-status">{status}</div>}
    {pending && <p role="status">Working…</p>}
    <fieldset disabled={pending}>
      {!token ? <section className="card workspace-auth">
        <h2>{registering ? "Create your workspace" : "Sign in to your workspace"}</h2>
        <p>Save tasks, plan around your availability, and check in with your study companion.</p>
        <form onSubmit={event => submit(event, async values => {
          const auth = await api.request<Auth>(registering ? "/api/v1/auth/register" : "/api/v1/auth/login", "POST", {
            email: text(values, "email"), password: text(values, "password"),
            ...(registering ? {
              name: text(values, "name"), timezone: deviceZone,
              birth_year: Number(text(values, "birth_year")), account_level: text(values, "account_level"),
            } : {}),
          });
          activeToken.current = auth.access_token;
          try { sessionStorage.setItem("pathly.session", auth.access_token); } catch { /* memory-only */ }
          setToken(auth.access_token);
        }, "Signed in.")}>
          {registering && <label>Your name<input name="name" required maxLength={80} autoComplete="name" /></label>}
          {registering && <label>Birth year<input name="birth_year" type="number" required min={1900}
            max={new Date().getFullYear()} autoComplete="bday-year" /></label>}
          {registering && <label>Account type<select name="account_level" defaultValue="university">
            <option value="university">University</option><option value="k12">K-12 student</option></select></label>}
          <label>Email<input name="email" type="email" required autoComplete="email" /></label>
          <label>Password<input name="password" type="password" required minLength={registering ? 8 : 1}
            pattern={registering ? "(?=.*[A-Za-z])(?=.*[0-9]).*" : undefined}
            title={registering ? "At least 8 characters with a letter and a digit" : undefined}
            maxLength={128} autoComplete={registering ? "new-password" : "current-password"} /></label>
          <button className="button primary">{registering ? "Create account" : "Sign in"}</button>
        </form>
        <button className="button" onClick={() => { setRegistering(!registering); setError(""); }}>
          {registering ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </section> : !data ? <section className="card workspace-auth">
        <p>{pending ? "Loading your workspace…" : "Your workspace could not be loaded."}</p>
        <button className="button primary" onClick={() => void run(refresh, "Workspace refreshed.")}>Retry</button>
        <button className="button" onClick={expire}>Return to sign in</button>
      </section> : <>
        <div className="workspace-toolbar">
          <div><h2>{data.user.name}'s workspace</h2><p>Calendar: {data.user.timezone} · Form times: {deviceZone}</p></div>
          <div className="workspace-actions">
            <button className="button" onClick={() => void run(refresh, "Workspace refreshed.", true)}>Refresh</button>
            <button className="button" onClick={() => void run(async () => {
              await api.request("/api/v1/auth/logout", "POST"); expire();
            }, "Signed out.")}>Sign out</button>
          </div>
        </div>
        <div className="workspace-stats" aria-label="This week's progress">
          <div className="card"><b>{data.report.completed_tasks}/{data.report.total_tasks}</b><p>Tasks due this week completed</p></div>
          <div className="card"><b>{data.report.completed_minutes} min</b><p>Study time checked in this week</p></div>
          <div className="card"><b>{data.report.missed_sessions}</b><p>Missed sessions this week</p></div>
        </div>
        <nav className="workspace-tabs" aria-label="Workspace sections">
          {["Planner", "Team", "Companion"].map(value => <button key={value} className={`button ${tab === value ? "primary" : ""}`}
            aria-current={tab === value ? "page" : undefined} onClick={() => setTab(value)}>{value}</button>)}
        </nav>
        {tab === "Planner" && <>
          <div className="workspace-grid">
            <section className="card">
              <h3>Add a goal</h3>
              <form onSubmit={event => submit(event, async (values, form) => {
                await api.request("/api/v1/goals", "POST", { title: text(values, "title") }); form.reset();
              }, "Goal added.")}>
                <label>Goal title<input name="title" required maxLength={200} /></label>
                <button className="button">Add goal</button>
              </form>
              <ul className="workspace-list">{data.goals.map(goal => <li key={goal.id}>{goal.title}</li>)}</ul>
            </section>
            <section className="card">
              <h3>Add a task</h3>
              <form onSubmit={event => submit(event, async (values, form) => {
                await api.request("/api/v1/tasks", "POST", {
                  title: text(values, "title"), duration_minutes: number(values, "minutes"),
                  priority: number(values, "priority"), due_at: iso(values, "due"), goal_id: text(values, "goal") || null,
                }); form.reset();
              }, "Task added. Preview a plan to schedule it.")}>
                <label>Task title<input name="title" required maxLength={200} /></label>
                <div className="workspace-row"><label>Minutes<input name="minutes" type="number" min={1} max={10080} defaultValue={45} required /></label>
                  <label>Priority<select name="priority" defaultValue="2"><option value="1">High</option><option value="2">Normal</option><option value="3">Low</option></select></label></div>
                <label>Deadline<input name="due" type="datetime-local" defaultValue={localAfter(1440)} required /></label>
                <label>Goal<select name="goal"><option value="">No goal</option>{data.goals.map(goal => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select></label>
                <button className="button primary">Add task</button>
              </form>
            </section>
            <section className="card">
              <h3>Your availability</h3>
              <p>Adding or removing availability clears future unchecked sessions. Preview a new plan afterwards.</p>
              <form onSubmit={event => submit(event, values => api.request("/api/v1/availability", "PUT", {
                windows: [...data.windows.map(({ starts_at, ends_at }) => ({ starts_at, ends_at })),
                  { starts_at: iso(values, "start"), ends_at: iso(values, "end") }],
              }), "Availability saved. Preview a new plan.")}>
                <label>Available from<input type="datetime-local" name="start" defaultValue={localAfter(15)} required /></label>
                <label>Available until<input type="datetime-local" name="end" defaultValue={localAfter(180)} required /></label>
                <button className="button">Add availability</button>
              </form>
              <ul className="workspace-list">{data.windows.map(window => <li key={window.id}>
                <span>{format(window.starts_at)} – {format(window.ends_at)}</span>
                <button className="button" aria-label={`Remove availability ${format(window.starts_at)}`} onClick={() => void run(() => api.request("/api/v1/availability", "PUT", {
                  windows: data.windows.filter(item => item.id !== window.id).map(({ starts_at, ends_at }) => ({ starts_at, ends_at })),
                }), "Availability removed. Preview a new plan.")}>Remove</button>
              </li>)}</ul>
            </section>
            <section className="card">
              <h3>Block busy time</h3><p>Conflicting future sessions will be cleared so you can replan them.</p>
              <form onSubmit={event => submit(event, values => api.request("/api/v1/busy-blocks", "POST", {
                title: text(values, "title"), starts_at: iso(values, "start"), ends_at: iso(values, "end"),
              }), "Busy time saved. Preview a new plan.")}>
                <label>Busy time title<input name="title" defaultValue="Class" required maxLength={200} /></label>
                <label>Busy from<input type="datetime-local" name="start" defaultValue={localAfter(60)} required /></label>
                <label>Busy until<input type="datetime-local" name="end" defaultValue={localAfter(90)} required /></label>
                <button className="button">Block time</button>
              </form>
              <ul className="workspace-list">{data.blocks.map(block => <li key={block.id}>
                <span>{block.title} · {format(block.starts_at)} – {format(block.ends_at)}</span>
                <button className="button" onClick={() => void run(() => api.request(`/api/v1/busy-blocks/${block.id}`, "DELETE"), "Busy time removed.")}>Remove</button>
              </li>)}</ul>
            </section>
          </div>
          <section className="card">
            <h3>Preview or replan your schedule</h3><p>Checked-in sessions are preserved. Past start times begin from the current minute. Review the proposal, then save it to your calendar.</p>
            <form onChange={() => setPreview(null)} onSubmit={event => submit(event, async values => {
              const starts_at = new Date(Math.max(Date.parse(iso(values, "start")), Math.floor(Date.now() / 60000) * 60000)).toISOString();
              const request = { starts_at, ends_at: iso(values, "end"),
                max_session_minutes: number(values, "session"), daily_limit_minutes: number(values, "daily") };
              const plan = await api.request<Plan>("/api/v1/schedule/replan", "POST", request);
              setPreview({ request, plan });
            }, "Preview ready. Review it before saving.")}>
              <div className="workspace-row"><label>Plan from<input name="start" type="datetime-local" defaultValue={localAfter(1)} required /></label>
                <label>Plan until<input name="end" type="datetime-local" defaultValue={localAfter(7 * 1440)} required /></label></div>
              <div className="workspace-row"><label>Maximum session (minutes)<input name="session" type="number" defaultValue={60} min={15} max={240} required /></label>
                <label>Daily study limit (minutes)<input name="daily" type="number" defaultValue={180} min={1} max={1440} required /></label></div>
              <button className="button">Preview plan</button>
            </form>
            {preview && <div className="workspace-proposal">
              <h4>Proposed sessions</h4>
              {preview.plan.expired_sessions > 0 && <p className="workspace-warning">
                Saving marks {preview.plan.expired_sessions} past unchecked session(s) as missed.
                If you studied them, record your check-in before replanning.
              </p>}
              {!preview.plan.entries.length && <p>No new sessions fit. Add availability or review your task deadlines.</p>}
              <ul className="workspace-list">{preview.plan.entries.map((entry, index) => <li key={index}>{taskName(entry.task_id)} · {format(entry.starts_at)} – {format(entry.ends_at)}</li>)}</ul>
              {preview.plan.unscheduled.map(item => <p className="workspace-warning" key={item.task_id}>
                {taskName(item.task_id)}: {item.minutes} min unscheduled ({item.reason.replaceAll("_", " ")}).
              </p>)}
              <button className="button primary" onClick={() => {
                const currentMinute = Math.floor(Date.now() / 60000) * 60000;
                const needsRefresh = Date.parse(preview.request.starts_at) < currentMinute;
                void run(async () => {
                  if (needsRefresh) {
                    if (Date.parse(preview.request.ends_at) <= currentMinute)
                      throw new Error("The planning window has ended. Choose a later end and preview again.");
                    const request = { ...preview.request, starts_at: new Date(currentMinute).toISOString() };
                    const plan = await api.request<Plan>("/api/v1/schedule/replan", "POST", request);
                    setPreview({ request, plan });
                  } else {
                    await api.request("/api/v1/schedule/replan", "POST", { ...preview.request, commit: true });
                    setPreview(null);
                  }
                }, needsRefresh ? "Time has advanced. Review the refreshed plan before saving."
                  : "Plan saved to your calendar.", true);
              }}>Save this plan</button>
            </div>}
          </section>
          <section className="card"><h3>Your tasks</h3>
            {!data.tasks.length && <p>No tasks yet. Add one above to begin.</p>}
            <ul className="workspace-list">{data.tasks.map(task => <li key={task.id}>
              <div><strong>{task.title}</strong><p>{task.status} · {task.completed_minutes}/{task.duration_minutes} min · Due {format(task.due_at)}{task.team_id ? " · Team task" : ""}</p></div>
              {task.status !== "completed" && <details><summary>Edit</summary>
                <form onSubmit={event => submit(event, values => api.request(`/api/v1/tasks/${task.id}`, "PATCH", {
                  title: text(values, "title"), priority: number(values, "priority"),
                  duration_minutes: number(values, "minutes"),
                }), "Task updated. Preview a new plan.")}>
                  <label>Title<input name="title" defaultValue={task.title} required maxLength={200} /></label>
                  <label>Minutes<input name="minutes" type="number" defaultValue={task.duration_minutes} min={Math.max(1, task.completed_minutes)} max={10080} required /></label>
                  <label>Priority<select name="priority" defaultValue={task.priority}><option value={1}>High</option><option value={2}>Normal</option><option value={3}>Low</option></select></label>
                  <button className="button">Save task</button>
                </form>
                <button className="button" onClick={() => void run(() => api.request(`/api/v1/tasks/${task.id}`, "PATCH", {
                  status: task.status === "cancelled" ? "pending" : "cancelled",
                }), "Task status updated.")}>{task.status === "cancelled" ? "Restore task" : "Cancel task"}</button>
              </details>}
            </li>)}</ul>
          </section>
          <section className="card"><h3>Calendar &amp; check-in</h3>
            {!data.entries.length && <p>Save a plan to add sessions to your calendar.</p>}
            <ul className="workspace-list">{data.entries.map(entry => <li key={entry.id}>
              <div><strong>{taskName(entry.task_id)}</strong><p>{format(entry.starts_at)} – {format(entry.ends_at)} · {entry.status}
                {entry.status === "completed" ? ` · ${entry.actual_minutes} min recorded` : ""}</p></div>
              {entry.status === "planned" && <form className="workspace-checkin" onSubmit={event => submit(event, values => api.request(`/api/v1/schedule/${entry.id}/check-in`, "POST", {
                status: "completed", actual_minutes: number(values, "minutes"),
              }), "Progress recorded.")}>
                <label>Minutes studied<input name="minutes" type="number" min={1} required
                  max={(Date.parse(entry.ends_at) - Date.parse(entry.starts_at)) / 60000}
                  defaultValue={(Date.parse(entry.ends_at) - Date.parse(entry.starts_at)) / 60000} /></label>
                <button className="button" disabled={Date.now() < Date.parse(entry.starts_at)}>Complete</button>
                <button className="button" type="button" disabled={Date.now() < Date.parse(entry.starts_at)} onClick={() => void run(() => api.request(`/api/v1/schedule/${entry.id}/check-in`, "POST", { status: "missed" }), "Marked missed. Preview a plan to reschedule.")}>Missed</button>
              </form>}
            </li>)}</ul>
          </section>
        </>}
        {tab === "Team" && <div className="workspace-grid">
          <section className="card"><h3>Team workspaces</h3>
            <form onSubmit={event => submit(event, async (values, form) => {
              const team = await api.request<Team>("/api/v1/teams", "POST", { name: text(values, "name") });
              setTeamId(team.id); form.reset();
            }, "Workspace created.")}>
              <label>Workspace name<input name="name" required maxLength={100} /></label><button className="button">Create workspace</button>
            </form>
            <label>Selected workspace<select value={teamId} onChange={event => setTeamId(event.target.value)}>
              <option value="">Choose a workspace</option>{data.teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select></label>
            {members.length > 0 && <p>Members: {members.map(member => member.name).join(", ")}</p>}
            {teamId && data.teams.find(team => team.id === teamId)?.owner_id === data.user.id && <form onSubmit={event => submit(event, async values => {
              const created = await api.request<{ code: string }>(`/api/v1/teams/${teamId}/invitations`, "POST", { email: text(values, "email") });
              setInviteCode(created.code);
            }, "Invitation created. Send the code below to the invitee.")}>
              <label>Invite by email<input type="email" name="email" required /></label><button className="button">Create invitation</button>
            </form>}
            {inviteCode && <p>Invitation code (shown once): <code>{inviteCode}</code></p>}
            <h4>Your invitations</h4>
            {!data.invitations.length && <p>No pending invitations.</p>}
            {data.invitations.map(invite => <form key={invite.id} className="workspace-row" onSubmit={event => submit(event, async values => {
              const team = await api.request<Team>(`/api/v1/invitations/${invite.id}/accept`, "POST", { code: text(values, "code") });
              setTeamId(team.id);
            }, "Invitation accepted.")}><p>Invitation to {invite.team_name}</p>
              <label>Code from the owner<input name="code" required maxLength={100} autoComplete="off" /></label>
              <button className="button">Accept invitation</button></form>)}
          </section>
          {teamId && <section className="card"><h3>Share or assign a task</h3>
            <p>Sharing makes a task visible to this workspace and removes its personal goal link. Previous unchecked sessions are cleared.</p>
            <form onSubmit={event => submit(event, values => api.request(`/api/v1/tasks/${text(values, "task")}/share`, "POST", {
              team_id: teamId, assignee_id: text(values, "member"),
            }), "Task shared. The assignee can now schedule it.")}>
              <label>Task<select name="task" required><option value="">Choose your task</option>
                {data.tasks.filter(task => task.owner_id === data.user.id && task.completed_minutes === 0 && task.status === "pending")
                  .map(task => <option key={task.id} value={task.id}>{task.title}</option>)}</select></label>
              <label>Assignee<select name="member" required><option value="">Choose a member</option>
                {members.map(member => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label>
              <button className="button primary">Share task</button>
            </form>
            <ul className="workspace-list">{data.tasks.filter(task => task.team_id === teamId).map(task => <li key={task.id}>
              <span>{task.title} · {members.find(member => member.id === task.assignee_id)?.name || "Member"} · {task.status}</span>
            </li>)}</ul>
          </section>}
          {teamId && <section className="card"><h3>Find common free time</h3><p>Uses every member's availability, busy time, and scheduled sessions.</p>
            <form onChange={() => setCommon(null)} onSubmit={event => submit(event, async values => {
              const slots = await api.request<{ starts_at: string; ends_at: string }[]>(`/api/v1/teams/${teamId}/coordinate`, "POST", {
                starts_at: iso(values, "start"), ends_at: iso(values, "end"), duration_minutes: number(values, "minutes"),
              }); setCommon(slots);
            }, "Common availability checked.")}>
              <label>Search from<input name="start" type="datetime-local" defaultValue={localAfter(1)} required /></label>
              <label>Search until<input name="end" type="datetime-local" defaultValue={localAfter(7 * 1440)} required /></label>
              <label>Minimum meeting length<input name="minutes" type="number" defaultValue={30} min={1} max={240} required /></label>
              <button className="button">Find free time</button>
            </form>
            {common && (common.length ? <ul className="workspace-list">{common.map((slot, index) => <li key={index}>{format(slot.starts_at)} – {format(slot.ends_at)}</li>)}</ul>
              : <p>No shared window fits. Ask each member to add availability.</p>)}
          </section>}
        </div>}
        {tab === "Companion" && <div className="workspace-grid">
          <section className="card"><h3>Your study companion</h3><p>Talk through your progress or mood. Schedule changes are reviewed in Planner.</p>
            <div className="workspace-chat" role="log" aria-label="Companion conversation" aria-live="polite">
              {!data.messages.length && <p>Tell your companion how studying is going today.</p>}
              {data.messages.map(message => <div key={message.id} className={`workspace-message ${message.role}`}><b>{message.role === "user" ? "You" : "Pathly"}</b><p>{message.content}</p></div>)}
              <div ref={chatEnd} />
            </div>
            {aiStatus && <p role="status">{aiStatus}</p>}
            <form onSubmit={event => submit(event, async (values, form) => {
              const reply = await api.request<ChatReply>("/api/v1/ai/chat", "POST", { message: text(values, "message"), mood: text(values, "mood") });
              setAiStatus(reply.provider === "llm" ? "AI response received." : reply.fallback_reason === "provider_unavailable"
                ? "The AI service is unavailable. Your companion replied in offline mode." : "Offline companion · AI service is not configured."); form.reset();
            }, "Reply received.")}>
              <label>How are you feeling?<select name="mood"><option value="neutral">Okay</option><option value="happy">Happy</option><option value="stressed">Stressed</option><option value="tired">Tired</option></select></label>
              <label>Message<textarea name="message" required maxLength={4000} rows={3} /></label>
              <button className="button primary">Send message</button>
            </form>
          </section>
          <section className="card"><h3>Companion preferences</h3>
            <form onSubmit={event => submit(event, values => api.request("/api/v1/me", "PATCH", {
              name: text(values, "name"), timezone: text(values, "timezone"), personality: text(values, "personality"),
            }), "Preferences saved.")}>
              <label>Display name<input name="name" defaultValue={data.user.name} required maxLength={80} /></label>
              <label>Calendar timezone<input name="timezone" defaultValue={data.user.timezone} required /></label>
              <label>Companion style<select name="personality" defaultValue={data.user.personality}><option value="warm">Warm</option><option value="direct">Direct</option><option value="playful">Playful</option></select></label>
              <button className="button">Save preferences</button>
            </form>
          </section>
        </div>}
        <section className="card"><h3>Notifications</h3><p>Session reminders appear here up to 15 minutes before the start, while the workspace is open.</p>
          {!data.notifications.filter(item => !item.read).length && <p>No unread notifications.</p>}
          <ul className="workspace-list">{data.notifications.filter(item => !item.read).map(item => <li key={item.id}><span>{item.message}</span>
            <button className="button" onClick={() => void run(() => api.request(`/api/v1/notifications/${item.id}/read`, "POST"), "Notification marked read.", true)}>Mark read</button>
          </li>)}</ul>
        </section>
      </>}
    </fieldset>
  </div>;
}
