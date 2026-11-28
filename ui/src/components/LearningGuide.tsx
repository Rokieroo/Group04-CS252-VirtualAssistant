import { useEffect, useState } from "react";
import { call } from "../api/backend";
type Preferences = { guide_enabled: boolean; weekly_reminder: boolean };

export function LearningGuide({ step }: { step: number }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState(""),
    [revision, retry] = useState(0),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    call<Preferences>("/me/learning-preferences")
      .then((p) => {
        if (active) setEnabled(p.guide_enabled);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [revision]);
  async function toggle() {
    setBusy(true);
    try {
      const p = await call<Preferences>("/me/learning-preferences", {
        method: "PATCH",
        body: JSON.stringify({ guide_enabled: !enabled }),
      });
      setEnabled(p.guide_enabled);
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const steps = [
    "Create or select a course.",
    "Upload a PDF syllabus or paste its content.",
    "Review the weekly plan, then confirm.",
    "Approve the roadmap and open the graph.",
    "Pick a stage to read and pin learning sources.",
  ];
  return (
    <section aria-label="Getting started guide" className="core-panel card learning-guide">
      {error ? (
        <p role="status">
          Could not load the guide.{" "}
          <button onClick={() => retry((v) => v + 1)}>Retry loading guide</button>
        </p>
      ) : enabled === null ? (
        <p role="status">Loading guide…</p>
      ) : (
        <>
          {enabled && (
            <>
              <h2>Getting started</h2>
              <progress
                aria-label="Getting started progress"
                value={step}
                max={5}
              />{" "}
              <strong>Step {step}/5</strong>
              <p>{steps[step - 1]}</p>
            </>
          )}
          <button disabled={busy} onClick={toggle}>
            {enabled ? "Dismiss guide" : "Show guide"}
          </button>
        </>
      )}
    </section>
  );
}
