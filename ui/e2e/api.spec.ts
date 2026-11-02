import { expect, test } from "@playwright/test";
import { checkFixture, resultFixture } from "../src/test/checkFixture";
import { signIn } from "./helpers";

test("API errors retry without demo fallback; answers are graded by the response", async ({
  page,
}) => {
  let loads = 0;
  const submissions: unknown[] = [];
  await page.route("**/api/v1/sessions/quiz/learning-check", async (route) => {
    loads++;
    await route.fulfill(
      loads === 1
        ? { status: 503, body: "unavailable" }
        : { json: { ...checkFixture, sessionId: "quiz" } },
    );
  });
  await page.route(
    "**/api/v1/learning-checks/check-1/attempts",
    async (route) => {
      submissions.push(route.request().postDataJSON());
      // Deliberately use a non-local grade: verifies the UI trusts the service, not its demo keys.
      await route.fulfill({
        json: {
          ...resultFixture,
          sessionId: "quiz",
          score: 25,
          passed: false,
          feedback: "Review the cited page.",
        },
      });
    },
  );
  await page.goto("/");
  await signIn(page);
  await expect(page.getByText("API checks · demo workspace")).toBeVisible();
  await page.getByRole("button", { name: "Take quiz", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("unavailable");
  await expect(page.getByRole("radio")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry loading" }).click();
  await expect(page.getByText(/test-lesson.pdf, page 2/)).toBeVisible();
  await page.getByRole("radio", { name: "went", exact: true }).check();
  await page.getByRole("button", { name: "Submit answers" }).click();
  await expect(page.getByRole("dialog").getByRole("status")).toContainText(
    "25% · Keep practicing",
  );
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({
    attemptId: expect.any(String),
    answers: [{ questionId: "q1", optionId: "went" }],
  });
  await page.keyboard.press("Escape");
  await expect(page.locator(".overview .metric-line")).toContainText("46%");
  await page.reload();
  await signIn(page);
  await expect(page.locator(".overview .metric-line")).toContainText("46%");
});

test("API empty checks and malformed responses have explicit states", async ({
  page,
}) => {
  let calls = 0;
  await page.route("**/api/v1/sessions/quiz/learning-check", (route) => {
    calls++;
    return route.fulfill({
      json:
        calls === 1
          ? { ...checkFixture, sessionId: "quiz", questions: [] }
          : { bad: "data" },
    });
  });
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: "Take quiz", exact: true }).click();
  await expect(page.getByText("No questions available yet")).toBeVisible();
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("alert")).toContainText("invalid response");
  await expect(page.getByRole("radio")).toHaveCount(0);
});
