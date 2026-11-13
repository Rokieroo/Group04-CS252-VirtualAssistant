import { expect, test, type Page } from "@playwright/test";
const parsed = {
  course: {
    code: { value: "CSC10014", source_page: 1 },
    title: { value: "Introduction to Virtual Assistants", source_page: 1 },
  },
  outcomes: [
    {
      code: "CLO1",
      text: "Frame the problem",
      bloom_level: "apply",
      source_page: 1,
    },
  ],
  weeks: [
    {
      week: 1,
      topics: ["Problem framing"],
      readings: ["Chapter 1"],
      source_page: 1,
    },
    { week: 2, topics: ["Retrieval"], source_page: 2 },
  ],
  assessments: [
    {
      title: "Final",
      weight: 90,
      due: "week 2",
      kind: "final",
      source_page: 2,
    },
  ],
  textbooks: [
    {
      title: "Course notes",
      authors: "Lecturer",
      required: true,
      source_page: 2,
    },
  ],
};
const pageText = {
  1: "CLO1: Frame the problem. Week 1: Problem framing",
  2: "Week 2: Retrieval. Final: 90%. Course notes by Lecturer",
};
async function backend(
  page: Page,
  options: { status?: number; code?: string; delay?: Promise<void> } = {},
) {
  const requests: { path: string; method: string; body: any }[] = [];
  let fail = options.status;
  await page.addInitScript(() =>
    sessionStorage.setItem("pathly.session", "test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    const body = req.headers()["content-type"]?.includes("application/json")
      ? req.postDataJSON()
      : req.postData();
    requests.push({ path, method: req.method(), body });
    if (path.endsWith("/courses"))
      return route.fulfill({
        json: [
          {
            id: "owned-csc10014",
            title: "CS252 - Computational Thinking",
          },
        ],
      });
    if (path.endsWith("/sources"))
      return route.fulfill({
        json:
          req.method() === "POST"
            ? {
                file_name: "CSC10014.pdf",
                pages: 2,
                status: "processed",
                kind: "syllabus",
              }
            : Object.entries(pageText).map(([page, text]) => ({
                file_name: "CSC10014.pdf",
                page: Number(page),
                text,
                kind: "syllabus",
              })),
      });
    if (path.endsWith("syllabus:parse")) {
      if (options.delay) await options.delay;
      if (fail) {
        const status = fail;
        fail = undefined;
        return route.fulfill({
          status,
          json: { detail: options.code ?? "failure" },
        });
      }
      return route.fulfill({
        json: {
          parsed,
          pages: 2,
          source_pages: pageText,
          status: "draft",
          warnings: [
            {
              code: "weights_sum",
              message: "Tổng trọng số là 90%",
              blocking: true,
              path: "assessments",
            },
          ],
        },
      });
    }
    if (path.endsWith("/syllabus") && req.method() === "GET")
      return route.fulfill({ status: 404, json: { detail: "Syllabus not found" } });
    if (path.endsWith("/syllabus"))
      return route.fulfill({
        status: 201,
        json: {
          id: "saved-syllabus",
          course_id: "owned-csc10014",
          raw_text: JSON.stringify(body.parsed),
          learning_outcomes: body.learning_outcomes,
          assessments: body.assessments,
        },
      });
    return route.fulfill({
      status: 500,
      json: { detail: "Unexpected request: " + path },
    });
  });
  return requests;
}
async function paste(page: Page) {
  await page.getByRole("button", { name: "Prefer text?" }).click();
  await page
    .getByRole("textbox", { name: "Syllabus text" })
    .fill("CSC10014 syllabus");
  await page.getByRole("button", { name: "Continue to review" }).click();
}
async function tabTo(page: Page, locator: ReturnType<Page["getByRole"]>) {
  for (let i = 0; i < 70; i++) {
    if (await locator.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error("Keyboard could not reach control");
}
test("PDF → four review tabs → citation → corrected confirmation payload", async ({
  page,
}) => {
  const requests = await backend(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Thêm đề cương", exact: true })
    .click();
  await page.getByLabel("Syllabus file", { exact: true }).setInputFiles({
    name: "CSC10014.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7"),
  });
  await page.getByRole("button", { name: "Continue to review" }).click();
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("button", { name: "Xác nhận đề cương", exact: true }),
  ).toBeDisabled();
  const cite = page.getByRole("button", { name: "tr. 1", exact: true }).last();
  await cite.click();
  await expect(page.getByRole("dialog")).toContainText("Frame the problem");
  await page.keyboard.press("Escape");
  await expect(cite).toBeFocused();
  await page.getByRole("tab", { name: "Chuẩn đầu ra", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Tuần & chủ đề", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("tab", { name: "Giáo trình", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByLabel("Tác giả", { exact: true }).fill("Updated lecturer");
  await page.getByRole("tab", { name: "Đánh giá", exact: true }).click();
  await page.getByLabel("Trọng số %", { exact: true }).fill("100");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Xác nhận đề cương", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Đã xác nhận", exact: true }),
  ).toBeVisible();
  const saved = requests.find((r) => r.path.endsWith("/syllabus"))!;
  expect(saved.body.parsed.textbooks[0].authors).toBe("Updated lecturer");
  expect(saved.body.parsed.weeks[0].readings).toEqual(["Chapter 1"]);
  expect(saved.body.parsed.source_pages[2]).toContain("Final");
  expect(saved.body.assessments[0].weight).toBe(100);
  expect(
    requests.find((r) => r.method === "POST" && r.path.endsWith("/sources"))
      ?.body,
  ).toContain('name="kind"');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("pasted text can be reviewed and confirmed using only keyboard", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Thêm đề cương", exact: true })
    .click();
  await tabTo(page, page.getByRole("button", { name: "Prefer text?" }));
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await page.keyboard.type("CSC10014 syllabus");
  await tabTo(page, page.getByRole("button", { name: "Continue to review" }));
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeFocused();
  await tabTo(
    page,
    page.getByRole("tab", { name: "Chuẩn đầu ra", exact: true }),
  );
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await tabTo(
    page,
    page.getByRole("spinbutton", { name: "Trọng số %", exact: true }),
  );
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("100");
  await tabTo(
    page,
    page.getByRole("button", { name: "Xác nhận đề cương", exact: true }),
  );
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Đã xác nhận", exact: true }),
  ).toBeVisible();
});
for (const [status, message] of [
  [400, "Tệp không hợp lệ"],
  [413, "Tệp lớn hơn 20 MB"],
  [415, "Chỉ hỗ trợ PDF hoặc DOCX"],
  [422, "Không nhận ra đề cương"],
] as const) {
  test(`HTTP ${status} shows Vietnamese error and allows retry`, async ({
    page,
  }) => {
    await backend(page, {
      status,
      code: status === 422 ? "not_a_syllabus" : "failure",
    });
    await page.goto("/");
    await page
      .getByRole("button", { name: "Thêm đề cương", exact: true })
      .click();
    await paste(page);
    await expect(page.getByRole("alert")).toContainText(message);
    await expect(page.getByRole("alert")).toBeFocused();
    await page.getByRole("button", { name: "Continue to review" }).click();
    await expect(
      page.getByRole("heading", { name: "Review your syllabus", exact: true }),
    ).toBeVisible();
  });
}
test("processing is indeterminate and prevents duplicate submission", async ({
  page,
}) => {
  let release!: () => void;
  const delay = new Promise<void>((r) => (release = r));
  await backend(page, { delay });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Thêm đề cương", exact: true })
    .click();
  await paste(page);
  await expect(page.getByRole("progressbar")).not.toHaveAttribute("value");
  await expect(
    page.getByRole("button", { name: "Continue to review" }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByRole("heading", { name: "Review your syllabus", exact: true }),
  ).toBeVisible();
});

test("roadmap edits survive approval and schedule opens S7", async ({
  page,
}) => {
  await backend(page);
  const nodes = [
    {
      id: "a",
      title: "Problem framing",
      type: "topic",
      week: 1,
      est_minutes: 90,
      status: "available",
    },
    {
      id: "b",
      title: "Retrieval",
      type: "topic",
      week: 2,
      est_minutes: 90,
      status: "locked",
    },
  ];
  let edges: any[] = [];
  let generated = 0;
  let saved = 0;
  await page.route("**/api/v1/**/roadmap:generate", (route) => {
    generated++;
    return route.fulfill({ json: { id: "rm1", nodes, edges: [] } });
  });
  await page.route("**/api/v1/roadmaps/rm1/edges", (route) => {
    if (route.request().method() === "POST") {
      const edge = {
        ...route.request().postDataJSON(),
        origin: "user",
        confidence: 1,
      };
      edges.push(edge);
      saved++;
      return route.fulfill({ status: 201, json: edge });
    }
    return route.fulfill({ json: edges });
  });
  await page.route("**/api/v1/roadmaps/rm1:schedule", (route) => {
    expect(route.request().postDataJSON()).toEqual({
      weekly_minutes: 300,
      max_daily_minutes: 120,
    });
    return route.fulfill({
      json: {
        tasks: [{ id: "task-a", title: "Problem framing" }],
        sessions: [
          { id: "s1", task_id: "task-a", starts_at: "2030-01-07T09:00:00Z" },
        ],
        unscheduled: [],
        overloaded_weeks: [],
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Thêm đề cương", exact: true })
    .click();
  await paste(page);
  await page.getByRole("tab", { name: "Đánh giá", exact: true }).click();
  await page.getByLabel("Trọng số %", { exact: true }).fill("100");
  await page
    .getByRole("button", { name: "Xác nhận đề cương", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Tạo roadmap →", exact: true })
    .click();
  await page.getByRole("tab", { name: "Graph tiên quyết" }).click();
  await page.getByLabel("Học trước", { exact: true }).selectOption("a");
  await page.getByLabel("Học sau", { exact: true }).selectOption("b");
  await page.getByRole("button", { name: "Thêm cạnh" }).click();
  await page.getByLabel("Học trước", { exact: true }).selectOption("b");
  await page.getByLabel("Học sau", { exact: true }).selectOption("a");
  await page.getByRole("button", { name: "Thêm cạnh" }).click();
  await expect(page.getByRole("alert")).toContainText("vòng lặp");
  await page
    .getByRole("button", { name: "Xác nhận roadmap", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Xem roadmap →", exact: true }),
  ).toBeVisible();
  expect(generated).toBe(1);
  expect(edges).toHaveLength(1);
  await page
    .getByRole("button", { name: "Xem roadmap →", exact: true })
    .click();
  await page.getByRole("button", { name: "Xếp vào lịch", exact: true }).click();
  await page.getByRole("button", { name: "Tạo lịch học", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "New roadmap sessions" }),
  ).toBeVisible();
  await expect(page.locator(".core-sessions")).toContainText("Problem framing");
  expect(saved).toBe(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("gradient fills survive scoped styles while account circles stay neutral", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Thêm đề cương", exact: true })
    .click();
  const settings = page.getByRole("button", {
    name: "Account settings",
    exact: true,
  });
  const avatars = page.locator(".avatar");
  const avatarBackgrounds = () =>
    avatars.evaluateAll((elements) =>
      elements.map((element) => getComputedStyle(element).background),
    );
  await settings.click();
  await page.getByText("Light", { exact: true }).click();
  await page.getByText("Violet", { exact: true }).click();
  const neutralLight = await avatarBackgrounds();
  await page.getByText("Visible Spectrum", { exact: true }).click();
  expect(await avatarBackgrounds()).toEqual(neutralLight);
  await page.getByRole("button", { name: "Close dialog" }).click();
  const action = page.locator(".core-drop .primary-action");
  const face = await action.evaluate(
    (element) => getComputedStyle(element, "::after").backgroundImage,
  );
  expect(face).toContain("rgb(0, 255, 118)");
  expect(face).toContain("rgb(255, 242, 0)");
  expect(
    await page
      .locator(".core-upload")
      .evaluate((element) => getComputedStyle(element).backgroundImage),
  ).toContain("linear-gradient");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute(
    "data-accent",
    "visible-spectrum",
  );
  await settings.click();
  await page.getByText("Dark", { exact: true }).click();
  const neutralDark = await avatarBackgrounds();
  await page.getByText("Neon Aura", { exact: true }).click();
  expect(await avatarBackgrounds()).toEqual(neutralDark);
  await page.getByText("Ocean", { exact: true }).click();
  await expect(page.locator("html")).not.toHaveAttribute(
    "data-gradient",
    "true",
  );
  await page.getByRole("button", { name: "Close dialog" }).click();
  expect(
    await page
      .locator(".core-upload")
      .evaluate((element) => getComputedStyle(element).backgroundImage),
  ).toBe("none");
});
