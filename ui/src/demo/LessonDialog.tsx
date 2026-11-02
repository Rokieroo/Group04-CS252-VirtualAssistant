import { useState } from "react";
import { checkSetup } from "../api/service";
import type { CheckResult } from "../api/types";
import { Button } from "../components/Button";
import { Modal } from "../components/Modal";
import { courseFor } from "./selectors";
import type { Session } from "./domain";
import { LearningCheck } from "../features/learning-check/LearningCheck";

type Props = {
  session: Session;
  previouslyVerified: boolean;
  onClose: () => void;
  onStudied: () => void;
  onComplete: (result: CheckResult) => void;
};
export function LessonDialog({
  session,
  previouslyVerified,
  onClose,
  onStudied,
  onComplete,
}: Props) {
  const [quiz, setQuiz] = useState(session.kind === "quiz");
  return (
    <Modal title={quiz ? "Knowledge check" : session.title} onClose={onClose}>
      <span className="pill">
        {courseFor(session.courseId).name} · {session.minutes} min
      </span>
      {quiz ? (
        checkSetup.config ? (
          <LearningCheck
            session={session}
            mode={checkSetup.config.mode}
            previouslyVerified={previouslyVerified}
            onComplete={onComplete}
          />
        ) : (
          <p role="alert" className="warning">
            {checkSetup.error}
          </p>
        )
      ) : (
        <>
          <h3>{session.title}</h3>
          <p>
            {session.courseId === "english"
              ? "Use past simple for completed actions: “I walked to school.” Use past continuous for an action in progress: “I was walking when it started raining.”"
              : "This is a sample lesson workspace. Course materials and subject-specific assessments can be connected here later."}
          </p>
          <div className="lesson-note">
            <h4>Try it yourself</h4>
            <p>Write one thing you learned and one question you still have.</p>
            <textarea
              aria-label="Lesson notes"
              placeholder="Your notes for this visit..."
            />
          </div>
          <div className="actions">
            <Button onClick={onStudied}>Mark as studied</Button>
            <Button primary onClick={() => setQuiz(true)}>
              Take knowledge check →
            </Button>
          </div>
          <p className="footnote">
            Reading alone does not increase verified progress.
          </p>
        </>
      )}
    </Modal>
  );
}
