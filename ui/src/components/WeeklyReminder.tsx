import { useEffect, useState } from "react";
import { call } from "../api/backend";

/** Show the Sunday reminder in an open session using the learner's server timezone. */
export function WeeklyReminder({ open }: { open: () => void }) {
  const [due, setDue] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const pref = await call<{
          reminder_due: boolean;
          seconds_to_change: number;
        }>("/me/weekly-reminder");
        if (!active) return;
        setDue(pref.reminder_due);
        timer = setTimeout(check, Math.max(1, pref.seconds_to_change || 60) * 1000);
      } catch {
        if (active) {
          setDue(false);
          timer = setTimeout(check, 60000);
        }
      }
    }
    void check();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  if (!due) return null;
  return (
    <aside className="card core-panel" aria-label="Weekly summary reminder">
      <p>Ready to review your study week?</p>
      <div className="core-actions">
        <button onClick={open}>View summary</button>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await call("/me/learning-preferences", {
                method: "PATCH",
                body: JSON.stringify({ weekly_reminder: false }),
              });
              setDue(false);
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Turn off summary reminder
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </aside>
  );
}
