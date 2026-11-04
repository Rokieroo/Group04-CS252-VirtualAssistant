// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { describe, expect, it } from "vitest";
import { createDemoCheckService } from "./checkService";

describe("demo learning checks", () => {
  it("preserves the sample English grading and returns explanations only after submission", async () => {
    const service = createDemoCheckService();
    const check = await service.load({ id: "past", courseId: "english" });
    expect(check.questions).toHaveLength(4);
    expect(
      check.questions.every((q) => !("correct" in q) && !("explanation" in q)),
    ).toBe(true);
    const answers = ["o1", "o0", "o2", "o1"].map((optionId, i) => ({
      questionId: `q${i}`,
      optionId,
    }));
    expect(
      await service.submit(check, { attemptId: "a1", answers }),
    ).toMatchObject({ score: 100, passed: true });
    expect(
      await service.submit(check, {
        attemptId: "a2",
        answers: answers.map((a) => ({ ...a, optionId: "o0" })),
      }),
    ).toMatchObject({ score: 25, passed: false });
  });
  it("labels non-English questions as a workflow demo and rejects incomplete or duplicate answers", async () => {
    const service = createDemoCheckService();
    const check = await service.load({ id: "math-0", courseId: "math" });
    expect(check.kind).toBe("workflow-demo");
    await expect(
      service.submit(check, { attemptId: "a1", answers: [] }),
    ).rejects.toThrow("every question");
    await expect(
      service.submit(check, {
        attemptId: "a1",
        answers: [
          { questionId: "q0", optionId: "o0" },
          { questionId: "q0", optionId: "o0" },
        ],
      }),
    ).rejects.toThrow("every question");
  });
});
