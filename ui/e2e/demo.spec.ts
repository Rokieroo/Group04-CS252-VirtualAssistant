import { expect, test } from "@playwright/test";
import { navigate, signIn } from "./helpers";

test("quiz credit persists and retakes cannot inflate it", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await signIn(page);
  await expect(page.getByText("Demo mode", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Take quiz", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Knowledge check" });
  for (const answer of ["went", "was", "They were playing.", "saw"])
    await dialog.getByRole("radio", { name: answer, exact: true }).check();
  await dialog.getByRole("button", { name: "Submit answers" }).click();
  await expect(dialog.getByRole("status")).toContainText("100% · Passed");
  await dialog.evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.screenshot({
    path: testInfo.outputPath("knowledge-check.png"),
    fullPage: false,
  });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.screenshot({
    path: testInfo.outputPath("knowledge-check-dark.png"),
  });
  await page.emulateMedia({ colorScheme: "light" });
  await dialog.getByRole("button", { name: "Practice again" }).click();
  for (const answer of ["went", "was", "They were playing.", "saw"])
    await dialog.getByRole("radio", { name: answer, exact: true }).check();
  await dialog.getByRole("button", { name: "Submit answers" }).click();
  await expect(dialog.getByRole("status")).toContainText("100% · Passed");
  await page.keyboard.press("Escape");
  await page.reload();
  await signIn(page);
  await expect(page.locator(".overview .metric-line")).toContainText("53%");
  await expect(
    page.getByRole("button", { name: "Retake quiz", exact: true }),
  ).toBeVisible();
  await navigate(page, "Mastery");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Mastery",
  );
  await expect(
    page.getByRole("heading", { name: "Assessment summary" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("Mastery cards open their own session and update after a check", async ({
  page,
}) => {
  await page.goto("/");
  await signIn(page);
  await navigate(page, "Mastery");

  const vocabulary = page
    .locator(".milestone")
    .filter({ hasText: "Vocabulary" });
  await expect(vocabulary).toContainText("Planned");
  await vocabulary.getByRole("button", { name: "Open lesson" }).click();
  await expect(page.getByRole("dialog", { name: "Vocabulary" })).toBeVisible();
  await page.keyboard.press("Escape");

  const quiz = page
    .locator(".milestone")
    .filter({ hasText: "Practice & short knowledge check" });
  await expect(quiz).toContainText("Planned");
  await quiz.getByRole("button", { name: "Take check" }).click();
  const dialog = page.getByRole("dialog", { name: "Knowledge check" });
  for (const answer of ["went", "was", "They were playing.", "saw"])
    await dialog.getByRole("radio", { name: answer, exact: true }).check();
  await dialog.getByRole("button", { name: "Submit answers" }).click();
  await expect(dialog.getByRole("status")).toContainText("100% · Passed");
  await page.keyboard.press("Escape");

  await expect(quiz).toContainText("Verified");
  await expect(
    quiz.getByRole("button", { name: "Retake check" }),
  ).toBeVisible();
  await expect(page.locator(".progress-summary").first()).toContainText("53%");
  await expect(page.locator(".progress-summary").first()).toContainText(
    "7 / 13",
  );
});

test("search, empty state, enrollment, navigation and calendar still work", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await signIn(page);
  await navigate(page, "Courses");
  await page
    .getByRole("textbox", { name: "Search modules" })
    .fill("no-such-subject");
  await expect(page.getByText("No modules match your search")).toBeVisible();
  await page.getByRole("button", { name: "Browse all modules" }).click();
  await page
    .getByRole("textbox", { name: "Search modules" })
    .fill("Mathematics");
  await page.getByRole("button", { name: "Choose module" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ask");
  await page.getByRole("button", { name: "I meet the prerequisite" }).click();
  await page.getByRole("button", { name: "Approve plan" }).click();
  await navigate(page, "Review");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await page.getByLabel("Calendar view").selectOption("Month");
  await expect(page.locator(".calendar.month")).toBeVisible();
  await expect(
    page.getByRole("button").filter({ hasText: "Fractions" }),
  ).toBeVisible();
  await page.getByRole("button").filter({ hasText: "Fractions" }).click();
  await expect(page.getByRole("dialog", { name: "Fractions" })).toBeVisible();
  await page.getByRole("button", { name: "Take knowledge check" }).click();
  await expect(page.getByText(/Demo workflow check only/)).toBeVisible();
  await page.keyboard.press("Escape");
  await navigate(page, "Courses");
  await expect(page.locator(".toast")).toBeHidden();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Courses",
  );
  await page.screenshot({
    path: testInfo.outputPath("library.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await navigate(page, "Review");
  await expect(page.getByLabel("Calendar view")).toHaveValue("Month");
  await page.screenshot({ path: testInfo.outputPath("review.png") });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.screenshot({ path: testInfo.outputPath("review-dark.png") });
});

test("mock login, upload and concept edits work across navigation", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Email", { exact: true })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await page.screenshot({ path: testInfo.outputPath("sign-in.png") });
  await signIn(page);
  await navigate(page, "Courses");
  const picker = page.getByLabel("Choose PDF files to upload");
  await picker.setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("demo"),
  });
  await expect(page.locator(".file-list .error")).toContainText("PDF");
  // Synthetic input for the current mock's signature/font/page checks; not a PDF parser test.
  await picker.setInputFiles({
    name: "demo-lesson.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(
      "%PDF-1.4\n/Font /Helvetica\n/Type /Page\n/Type /Page\n%%EOF",
    ),
  });
  await expect(page.locator(".file-list .processed")).toContainText("2 pages");
  await expect(page.locator(".concept-list > li")).toHaveCount(10);
  await page
    .getByRole("textbox", { name: "Rename Framing ladder", exact: true })
    .fill("Updated concept");
  await page
    .getByRole("button", { name: "Delete Updated concept", exact: true })
    .click();
  await expect(page.locator(".concept-list > li")).toHaveCount(9);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.locator(".concept-list > li")).toHaveCount(10);
  await page.getByRole("button", { name: "Confirm all", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "All confirmed" }),
  ).toBeDisabled();
  await navigate(page, "Companion");
  await expect(
    page.getByRole("heading", { name: "Choose a mode" }),
  ).toBeVisible();
  await navigate(page, "Courses");
  await expect(
    page.getByRole("textbox", { name: "Rename Updated concept", exact: true }),
  ).toHaveValue("Updated concept");
  await expect(
    page.getByRole("button", { name: "All confirmed" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("course-concepts.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
