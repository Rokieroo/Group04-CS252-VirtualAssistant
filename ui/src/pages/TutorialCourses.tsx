import { useEffect, useState } from "react";
import { Modal } from "../components/Modal";

export const tutorial = {
  id: "builtin:getting-started:v1",
  origin: "library" as const,
  title: "Getting Started",
  verified: true,
  lessons: [
    {
      title: "Add your syllabus",
      text: "Open Courses. Upload PDF or DOCX, or paste syllabus text. Continue to review the extracted content.",
    },
    {
      title: "Review before confirming",
      text: "Use the four review tabs to correct outcomes, weeks, assessments and textbooks. Open a page citation to check the source and resolve blocking warnings before confirming.",
    },
    {
      title: "Explore your roadmap",
      text: "Select a week to inspect topics and milestones. Use Graph prerequisites to review or change the learning order. Cyclic prerequisites are rejected.",
    },
    {
      title: "Plan your study time",
      text: "After approving a roadmap, choose Xếp vào lịch and enter weekly and daily study limits. Schedule shows sessions and any work that could not fit. The live planner needs your availability.",
    },
  ],
};
const key = "pathly.preview.tutorial-enrollment.v1";
type Enrollment = { initialized: true; enrolled: boolean };
function initial(): Enrollment {
  try {
    const value = localStorage.getItem(key);
    if (value) {
      const state = JSON.parse(value);
      if (state.initialized === true && typeof state.enrolled === "boolean")
        return state;
    }
  } catch {
    /* Storage may be unavailable; use session state and explain on save. */
  }
  return { initialized: true, enrolled: true };
}

/** Preview enrollment only; live enrollment awaits a catalog/ownership contract. */
export function TutorialCourses({
  location,
  mock,
  onEnrollmentChange,
}: {
  location: "library" | "roadmap";
  mock: boolean;
  onEnrollmentChange?: (enrolled: boolean) => void;
}) {
  const [state, setState] = useState<Enrollment>(() => {
    const state = initial();
    if (mock) {
      try {
        localStorage.setItem(key, JSON.stringify(state));
      } catch {
        /* Save reports storage failures below. */
      }
    }
    return state;
  });
  useEffect(() => {
    onEnrollmentChange?.(mock && state.enrolled);
  }, [mock, state.enrolled, onEnrollmentChange]);
  const [remove, setRemove] = useState(false);
  const [edit, setEdit] = useState(false);
  const [lesson, setLesson] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  function enroll(enrolled: boolean) {
    const next: Enrollment = { initialized: true, enrolled };
    try {
      localStorage.setItem(key, JSON.stringify(next));
      setState(next);
      setMessage(
        enrolled
          ? "Getting Started enrolled."
          : "Getting Started removed from Roadmap. It remains available in Library.",
      );
      setRemove(false);
    } catch {
      setMessage(
        "Could not save enrollment in this browser. Please enable site storage and retry.",
      );
    }
  }
  if (location === "roadmap" && mock && !state.enrolled)
    return (
      <section className="card core-panel">
        <h2>Prepared courses</h2>
        <p>
          Getting Started is available in Library. Enroll there to add it to
          your Roadmap.
        </p>
      </section>
    );
  return (
    <section className="card core-panel" aria-label="Prepared courses">
      <h2>
        {location === "library" ? "Prepared courses" : "Your prepared courses"}
      </h2>
      <p>
        {mock
          ? "Preview catalog · Enrollment is saved in this browser's shared preview profile, not a signed-in account."
          : "Catalog preview · Account enrollment requires backend integration."}
      </p>
      <article>
        <h3>{tutorial.title}</h3>
        <p>Library-provided · Verified syllabus · Four short lessons</p>
        <p>
          {mock
            ? state.enrolled
              ? "Enrolled"
              : "Not enrolled"
            : "Enrollment unavailable"}
        </p>
        {location === "library" && (
          <button
            disabled={!mock || state.enrolled}
            onClick={() => enroll(true)}
          >
            {mock && state.enrolled ? "Enrolled" : "Enroll"}
          </button>
        )}
        {location === "roadmap" && (
          <div className="core-actions">
            <button onClick={() => setEdit(true)}>Edit Getting Started</button>
            <button disabled={!mock} onClick={() => setRemove(true)}>
              Remove Getting Started
            </button>
          </div>
        )}
        {location === "roadmap" && mock && state.enrolled && (
          <ol>
            {tutorial.lessons.map((item, index) => (
              <li key={item.title}>
                <button onClick={() => setLesson(index)}>{item.title}</button>
                <span> · 2 min</span>
              </li>
            ))}
          </ol>
        )}
        {!mock && (
          <p>
            Prepared-course origin, enrollment and one-time account
            initialization are not supported by the current API.
          </p>
        )}
      </article>
      {message && <p role="status">{message}</p>}
      {remove && (
        <Modal
          title={`Remove ${tutorial.title}?`}
          onClose={() => setRemove(false)}
        >
          <p>
            This removes Getting Started from your Roadmap. It stays in Library
            as not enrolled, so you can enroll again. Its prepared lessons
            remain available.
          </p>
          <div className="core-actions">
            <button autoFocus onClick={() => setRemove(false)}>
              Cancel
            </button>
            <button onClick={() => enroll(false)}>Remove</button>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={`Edit ${tutorial.title}`} onClose={() => setEdit(false)}>
          <p>
            Editing rules for prepared courses are not defined yet. Which fields
            learners may change, and whether those changes should survive
            re-enrollment, needs a product decision.
          </p>
          <button onClick={() => setEdit(false)}>Close</button>
        </Modal>
      )}
      {lesson !== null && (
        <Modal
          title={tutorial.lessons[lesson].title}
          onClose={() => setLesson(null)}
        >
          <p>{tutorial.lessons[lesson].text}</p>
          <button onClick={() => setLesson(null)}>Close lesson</button>
        </Modal>
      )}
    </section>
  );
}
