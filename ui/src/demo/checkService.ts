// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import type { LearningCheck, LearningCheckService } from "../api/types";

// Public demo only. These answer keys are bundled locally and are NOT secure grading.
const questionsFor = (courseId: string) =>
  courseId === "english"
    ? [
        {
          q: "Yesterday, she ___ to school.",
          options: ["go", "went", "going"],
          correct: 1,
          explanation: "“Went” is the past simple form of “go”.",
        },
        {
          q: "I ___ studying when the phone rang.",
          options: ["was", "am", "were"],
          correct: 0,
          explanation:
            "“I was studying” describes an action in progress in the past.",
        },
        {
          q: "Which sentence uses past continuous?",
          options: ["They played.", "They play.", "They were playing."],
          correct: 2,
          explanation: "Past continuous uses was/were + verb-ing.",
        },
        {
          q: "While I was walking, I ___ a friend.",
          options: ["see", "saw", "seeing"],
          correct: 1,
          explanation: "The short event uses past simple: “saw”.",
        },
      ]
    : [
        {
          q: "What should you do before moving to the next topic?",
          options: [
            "Check your understanding",
            "Skip the assessment",
            "Only log study time",
          ],
          correct: 0,
          explanation: "Understanding is checked through an assessment.",
        },
        {
          q: "How does verified progress increase in this demo?",
          options: [
            "By opening a lesson",
            "By passing a check",
            "By adding a course",
          ],
          correct: 1,
          explanation: "A passing check is required.",
        },
      ];

export function createDemoCheckService(): LearningCheckService {
  const loaded = new Map<
    string,
    { check: LearningCheck; keys: ReturnType<typeof questionsFor> }
  >();
  return {
    async load(session, signal) {
      signal?.throwIfAborted();
      const keys = questionsFor(session.courseId);
      const check: LearningCheck = {
        id: `demo:${session.id}`,
        sessionId: session.id,
        title: "Knowledge check",
        kind: session.courseId === "english" ? "subject" : "workflow-demo",
        questions: keys.map((q, i) => ({
          id: `q${i}`,
          prompt: q.q,
          options: q.options.map((text, j) => ({ id: `o${j}`, text })),
          citations: [],
        })),
      };
      loaded.set(check.id, { check, keys });
      return check;
    },
    async submit(check, submission, signal) {
      signal?.throwIfAborted();
      const entry = loaded.get(check.id);
      if (
        !entry ||
        submission.answers.length !== entry.check.questions.length ||
        new Set(submission.answers.map((a) => a.questionId)).size !==
          entry.check.questions.length ||
        !entry.check.questions.every((q) =>
          submission.answers.some(
            (a) =>
              a.questionId === q.id &&
              q.options.some((o) => o.id === a.optionId),
          ),
        )
      )
        throw new Error("Answer every question before submitting.");
      const correct = entry.keys.filter((q, i) =>
        submission.answers.some(
          (a) => a.questionId === `q${i}` && a.optionId === `o${q.correct}`,
        ),
      ).length;
      const score = Math.round((correct / entry.keys.length) * 100);
      return {
        checkId: check.id,
        sessionId: entry.check.sessionId,
        score,
        passed: score >= 70,
        feedback:
          score >= 70
            ? "This demo session earns credit once. Retakes do not add extra credit."
            : "Review the explanations and try again.",
        explanations: entry.keys.map((q, i) => ({
          questionId: `q${i}`,
          text: q.explanation,
        })),
      };
    },
  };
}
