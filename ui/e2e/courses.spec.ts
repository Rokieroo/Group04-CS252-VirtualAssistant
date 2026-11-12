import { expect, test, type Page } from "@playwright/test";
import { navigate } from "./helpers";
import AxeBuilder from "@axe-core/playwright";

// API-contract fixtures, not production persistence. Server ownership is covered in pytest.
async function backend(page: Page) {
  const requested: string[] = [];
  let failList = true;
  let courses = [
    { id: "course-a", title: "Same title", level: "university" },
    { id: "course-b", title: "Same title", level: "k12" },
  ];
  const saved = (id: string) => ({
    id,
    course_id: "course-a",
    title: id === "new" ? "Latest roadmap" : "Earlier roadmap",
    created_at: "2026-11-11T00:00:00Z",
    nodes: [],
    edges: [],
  });
  await page.addInitScript(() =>
    sessionStorage.setItem("pathly.session", "fixture-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    requested.push(`${req.method()} ${path}`);
    if (path.endsWith("/courses") && req.method() === "POST") {
      const course = {
        id: "created-course",
        level: "university",
        ...req.postDataJSON(),
      };
      courses.push(course);
      return route.fulfill({ status: 201, json: course });
    }
    if (path.endsWith("/courses")) {
      if (failList) {
        return route.fulfill({
          status: 503,
          json: { detail: "Temporarily unavailable" },
        });
      }
      return route.fulfill({ json: courses });
    }
    if (path.endsWith("/course-a/syllabus"))
      return route.fulfill({
        json: {
          id: "saved-a",
          course_id: "course-a",
          raw_text: "Stored personal syllabus",
          learning_outcomes: [],
          assessments: [],
        },
      });
    if (path.endsWith("/course-a/roadmaps"))
      return route.fulfill({ json: [saved("new"), saved("old")] });
    if (path.endsWith("/course-b/roadmaps")) return route.fulfill({ json: [] });
    if (/\/roadmaps\/(old|new)$/.test(path))
      return route.fulfill({
        json: saved(path.endsWith("old") ? "old" : "new"),
      });
    if (path.endsWith("/edges")) return route.fulfill({ json: [] });
    if (path.endsWith("/graph/layout"))
      return route.fulfill({ json: { positions: [] } });
    if (path.endsWith("/graph"))
      return route.fulfill({ json: { nodes: [], edges: [] } });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  return {
    requested,
    recover: () => {
      failList = false;
    },
  };
}

async function openList(page: Page, recover: () => void) {
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Temporarily unavailable",
  );
  recover();
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.locator(".course-library-card")).toHaveCount(2);
}

test("owned courses retry, discover every saved roadmap, reopen and reload", async ({
  page,
}) => {
  const { requested, recover } = await backend(page);
  await openList(page, recover);
  const cards = page.locator(".course-library-card");
  await cards.nth(1).getByRole("button", { name: "Lộ trình đã lưu" }).click();
  await expect(cards.nth(1)).toContainText("Chưa có lộ trình đã lưu");
  await cards.first().getByRole("button", { name: "Lộ trình đã lưu" }).click();
  await expect(cards.first().locator("li")).toHaveCount(2);
  await page.screenshot({
    path: test.info().outputPath("saved-roadmaps.png"),
    fullPage: true,
  });
  await cards
    .first()
    .locator("li")
    .filter({ hasText: "Earlier roadmap" })
    .getByRole("button", { name: "Mở lộ trình" })
    .click();
  await expect(page).toHaveURL(/course=course-a.*kg_roadmap=old.*#roadmap/);
  await expect
    .poll(() => requested.includes("GET /api/v1/roadmaps/old/graph"))
    .toBe(true);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Edit course syllabus", exact: true }),
  ).toBeVisible();
  expect(
    requested.filter((r) => r === "GET /api/v1/roadmaps/old").length,
  ).toBeGreaterThanOrEqual(2);
  expect(requested.some((r) => r.startsWith("POST"))).toBe(false);
});

test("duplicate titles retain distinct IDs and course creation uses the chosen ID", async ({
  page,
}) => {
  const { requested, recover } = await backend(page);
  await openList(page, recover);
  await page
    .locator(".course-library-card")
    .nth(1)
    .getByRole("button", { name: "Mở đề cương", exact: true })
    .click();
  await expect(page).toHaveURL(/course=course-b/);
  await expect(page.locator(".core-upload")).toBeVisible();
  await expect
    .poll(() => requested.includes("GET /api/v1/courses/course-b/syllabus"))
    .toBe(true);
  await page.getByRole("button", { name: "Đổi môn học", exact: true }).click();
  await page
    .getByLabel("Tên môn học", { exact: true })
    .fill("New personal course");
  await page.getByRole("button", { name: "Tạo môn học", exact: true }).click();
  await expect(page).toHaveURL(/course=created-course/);
  await expect(page.locator(".core-upload")).toBeVisible();
  expect(requested.filter((r) => r === "POST /api/v1/courses")).toHaveLength(1);
});

test("course list fits the viewport and exposes accessible controls", async ({
  page,
}) => {
  const { recover } = await backend(page);
  await openList(page, recover);
  if (test.info().project.name.endsWith("mobile"))
    await page.setViewportSize({ width: 360, height: 844 });
  await expect(page.locator(".course-library")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    (await new AxeBuilder({ page }).include(".course-library").analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({
    path: test.info().outputPath("courses.png"),
    fullPage: true,
  });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((a) =>
          Number.isFinite(Number(a.effect?.getComputedTiming().endTime)),
        )
        .map((a) => a.finished.catch(() => {})),
    );
  });
  expect(
    (await new AxeBuilder({ page }).include(".course-library").analyze())
      .violations,
  ).toEqual([]);
});

test("saved syllabus resumes from the selected course after reload", async ({
  page,
}) => {
  const { requested, recover } = await backend(page);
  await openList(page, recover);
  await page
    .locator(".course-library-card")
    .first()
    .getByRole("button", { name: "Mở đề cương", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeVisible();
  expect(
    requested.filter((r) => r === "GET /api/v1/courses/course-a/syllabus")
      .length,
  ).toBeGreaterThanOrEqual(2);
  expect(requested.some((r) => r.startsWith("POST"))).toBe(false);
});

test("browser back restores the previous course instead of keeping another course's editor", async ({
  page,
}) => {
  const { recover } = await backend(page);
  await openList(page, recover);
  await page
    .locator(".course-library-card")
    .first()
    .getByRole("button", { name: "Mở đề cương", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeVisible();
  await navigate(page, "Roadmap");
  await navigate(page, "Courses");
  await page.getByRole("button", { name: "Đổi môn học", exact: true }).click();
  await page
    .locator(".course-library-card")
    .nth(1)
    .getByRole("button", { name: "Mở đề cương", exact: true })
    .click();
  await expect(page.locator(".core-upload")).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/course=course-a.*#roadmap/);
  await navigate(page, "Courses");
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeVisible();
});

test("creating a course preserves every path and switching graphs survives reload", async ({
  page,
}) => {
  const { recover, requested } = await backend(page);
  await page.route("**/course-b/roadmaps", (route) =>
    route.fulfill({
      json: [
        {
          id: "b-map",
          course_id: "course-b",
          nodes: [{ id: "b1", title: "B checkpoint" }],
        },
      ],
    }),
  );
  await page.route("**/roadmaps/b-map", (route) =>
    route.fulfill({
      json: {
        id: "b-map",
        course_id: "course-b",
        title: "B roadmap",
        nodes: [{ id: "b1", title: "B checkpoint" }],
      },
    }),
  );
  await page.route("**/created-course/roadmaps", (route) =>
    route.fulfill({ json: [] }),
  );
  await openList(page, recover);
  await page.getByLabel("Tên môn học", { exact: true }).fill("Third course");
  await page.getByRole("button", { name: "Tạo môn học", exact: true }).click();
  await expect(page).toHaveURL(/course=created-course/);
  await navigate(page, "Roadmap");
  const cards = page.locator(".root-course-card");
  await expect(page.locator("[data-course-path]")).toHaveCount(3);
  await expect(cards.nth(2)).toContainText("Continue course setup");
  for (const [index, id] of [
    [1, "b-map"],
    [0, "new"],
  ] as const) {
    await cards.nth(index).click();
    await expect(page).toHaveURL(new RegExp("kg_roadmap=" + id));
    await expect
      .poll(() => requested.includes("GET /api/v1/roadmaps/" + id + "/graph"))
      .toBe(true);
    await expect(page.locator("[data-course-path]")).toHaveCount(3);
  }
  await page.reload();
  await expect(page.locator("[data-course-path]")).toHaveCount(3);
  await expect(
    page.getByRole("button", { name: "Edit course syllabus" }),
  ).toBeVisible();
  await expect(cards.first()).toHaveAttribute("aria-pressed", "true");
});
