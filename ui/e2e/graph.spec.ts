import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
const nodes = [
  {
    id: "a",
    title: "Z Foundations",
    type: "topic",
    kind: "topic",
    week: 1,
    est_minutes: 60,
    duration_minutes: 60,
    covers: [],
    roadmap_id: "rm",
  },
  {
    id: "b",
    title: "A Retrieval",
    type: "topic",
    kind: "topic",
    week: 2,
    est_minutes: 90,
    duration_minutes: 90,
    covers: [],
    roadmap_id: "rm",
  },
  {
    id: "c",
    title: "Other topic",
    type: "topic",
    kind: "topic",
    week: 3,
    est_minutes: 40,
    duration_minutes: 40,
    covers: [],
    roadmap_id: "rm",
  },
  {
    id: "exam",
    title: "Midterm",
    type: "milestone",
    kind: "milestone",
    week: 4,
    est_minutes: 30,
    duration_minutes: 30,
    covers: ["b"],
    roadmap_id: "rm",
  },
];
async function backend(page: Page, courseNodes = nodes) {
  page.on("pageerror", (e) => console.log("GRAPH PAGE ERROR", e.stack));
  let positions: { node_id: string; x: number; y: number; pinned: boolean }[] =
    [];
  const requested: string[] = [];
  let savedSyllabus = {
    id: "saved-syllabus",
    syllabus_id: "saved-syllabus",
    course_id: "c1",
    created_at: "2026-11-11T00:00:00Z",
    raw_text: JSON.stringify({
      file_name: "Review syllabus.txt",
      original_text: "Original syllabus source",
      course: { title: { value: "Graph course" } },
      source_pages: { 1: "Syllabus page one" },
      weeks: nodes.map((n) => ({
        week: n.week,
        topics: [n.title],
        source_page: 1,
      })),
      outcomes: [
        {
          code: "CLO1",
          text: "Understand the foundations",
          description: "Understand the foundations",
          source_page: 1,
        },
      ],
      assessments: [
        {
          name: "Midterm",
          title: "Midterm",
          weight: 100,
          due_week: 4,
          source_page: 1,
        },
      ],
      textbooks: [],
    }),
    learning_outcomes: [
      {
        id: "outcome",
        syllabus_id: "saved-syllabus",
        code: "CLO1",
        description: "Understand the foundations",
        bloom_level: "understand",
      },
    ],
    assessments: [
      {
        id: "exam",
        syllabus_id: "saved-syllabus",
        name: "Midterm",
        weight: 100,
        due_week: 4,
      },
    ],
  };
  const pages = [
    {
      id: "s1",
      file_name: "Lecture notes.txt",
      page: 1,
      text: "Private lecture page one",
      kind: "material",
    },
    {
      id: "s2",
      file_name: "Lecture notes.txt",
      page: 2,
      text: "Private lecture page two",
      kind: "material",
    },
    {
      id: "s3",
      file_name: "Extra notes.txt",
      page: 1,
      text: "Extra private notes",
      kind: "material",
    },
  ];

  const courseEdges =
    courseNodes === nodes
      ? [
          {
            parent_id: "a",
            child_id: "b",
            kind: "strict",
            origin: "user",
            confidence: 1,
          },
        ]
      : courseNodes.slice(1).map((n, i) => ({
          parent_id: courseNodes[i].id,
          child_id: n.id,
          kind: "strict",
          origin: "user",
          confidence: 1,
        }));
  await page.addInitScript(() =>
    sessionStorage.setItem("pathly.session", "test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname;
    requested.push(path + url.search);
    if (path.endsWith("/graph/edges") && req.method() === "POST") {
      const edge = { ...req.postDataJSON(), origin: "user", confidence: 1 };
      courseEdges.push(edge);
      return route.fulfill({ status: 201, json: edge });
    }
    if (path.includes("/graph/edges/") && req.method() === "DELETE") {
      const [parent, child] = path.split("/graph/edges/")[1].split("/");
      const index = courseEdges.findIndex(
        (e) => e.parent_id === parent && e.child_id === child,
      );
      if (index >= 0) courseEdges.splice(index, 1);
      return route.fulfill({ status: 204 });
    }

    if (/\/courses\/c1\/syllabus(?:\/saved-syllabus)?$/.test(path)) {
      if (req.method() === "PUT") {
        const body = req.postDataJSON();
        savedSyllabus = {
          ...savedSyllabus,
          raw_text: JSON.stringify(body.parsed),
          learning_outcomes: body.learning_outcomes,
          assessments: body.assessments,
        };
      }
      return route.fulfill({ json: savedSyllabus });
    }
    if (path.endsWith("/materials"))
      return route.fulfill({
        json: {
          files: path.includes("/b/")
            ? [
                {
                  file_name: "Lecture notes.txt",
                  status: "attached",
                  pages: [
                    {
                      source_id: "s2",
                      page: 2,
                      confidence: 1,
                      method: "manual",
                    },
                  ],
                },
              ]
            : [],
        },
      });
    if (path.endsWith("/resources"))
      return route.fulfill({
        json: {
          status: "insufficient",
          gaps: [],
          resources: [
            {
              id: "r1",
              rank: 1,
              title: "One verified reading",
              url: "https://ocw.mit.edu/reading",
              domain: "ocw.mit.edu",
              format: "article",
              language: "en",
              duration_min: 10,
              is_free: true,
              score: 0.8,
              breakdown: {},
              reason: "Matches this topic",
              evidence_quote: "Relevant source excerpt",
              pinned: false,
            },
          ],
        },
      });
    if (path.endsWith("/courses"))
      return route.fulfill({
        json: [{ id: "c1", title: "CS252 - Computational Thinking" }],
      });
    if (path.includes("/concepts/") && path.endsWith("/sources")) {
      const personal = path.includes("/b/");
      return route.fulfill({
        json: {
          node_id: personal ? "b" : "a",
          status: "ready",
          user_material_count: personal ? 2 : 0,
          source_count: 2,
          sources: personal
            ? [
                {
                  kind: "user_material",
                  id: "private-1",
                  source_id: "s1",
                  title: "Lecture notes.txt",
                  url: null,
                  pages: [1, 2],
                  provider: "User upload",
                  format: "pdf",
                  reason: "Your course material",
                  verification_status: "user_material",
                  license: "private",
                },
                {
                  kind: "user_material",
                  id: "private-2",
                  source_id: "s3",
                  title: "Extra notes.txt",
                  url: null,
                  pages: [1],
                  provider: "User upload",
                  format: "pdf",
                  reason: "Your course material",
                  verification_status: "user_material",
                  license: "private",
                },
              ]
            : [
                {
                  kind: "catalog",
                  id: "catalog-1",
                  title: "Verified reading",
                  url: "https://ocw.mit.edu/reading",
                  pages: [],
                  provider: "MIT OCW",
                  institution: "Massachusetts Institute of Technology",
                  license: "CC-BY-4.0",
                  format: "article",
                  duration_min: 20,
                  score: 0.9,
                  reason: "Matches the foundations",
                  verification_status: "verified",
                },
              ],
        },
      });
    }
    if (path.endsWith("/sources")) return route.fulfill({ json: pages });
    if (path.endsWith("/roadmaps/rm"))
      return route.fulfill({
        json: {
          id: "rm",
          course_id: "c1",
          nodes: courseNodes,
          edges: courseEdges,
        },
      });
    if (path.endsWith("/roadmaps/rm/edges"))
      return route.fulfill({
        json: courseEdges,
      });
    if (path.endsWith("/graph/layout")) {
      if (req.method() === "PUT") positions = req.postDataJSON().positions;
      return route.fulfill({ json: { positions, saved: positions.length } });
    }
    if (path.endsWith("/graph")) {
      const graphNodes = courseNodes.map(({ covers, ...n }, i) => ({
        ...n,
        status: i === 0 ? "completed" : "pending",
        outcome_ids: [i < 2 ? "CLO1" : "CLO2"],
        source_count: i < 2 ? 2 : 0,
        user_material_count: i === 1 ? 2 : 0,
        sources_status: i < 2 ? "ready" : "insufficient",
        layer: i + 1,
      }));
      return route.fulfill({
        json: {
          nodes: path.includes("/roadmap-nodes/")
            ? graphNodes.slice(0, 2)
            : graphNodes,
          edges: [
            ...courseEdges.map((e) => ({
              ...e,
              parent: e.parent_id,
              child: e.child_id,
            })),
            ...(courseNodes === nodes
              ? [
                  {
                    parent: "b",
                    child: "exam",
                    kind: "covers",
                    origin: "milestone_covers",
                    confidence: 1,
                  },
                ]
              : []),
          ],
        },
      });
    }
    if (path.endsWith("/exercises"))
      return route.fulfill({ json: { exercises: [], count: 0 } });
    return route.fulfill({
      json: { status: "ready", sources: [], resources: [], gaps: [] },
    });
  });
  return {
    requested,
    get positions() {
      return positions;
    },
  };
}
test("CLO/source filters and URL selection restore after reload, with server local graph", async ({
  page,
}) => {
  const api = await backend(page);
  await page.goto("/?kg_roadmap=rm#roadmap");
  await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
  await page.getByRole("button", { name: "📋 Danh sách" }).click();
  await page.getByRole("combobox", { name: "CLO:" }).selectOption("CLO1");
  await page.getByLabel(/Nguồn đã kiểm chứng/).check();
  await expect(
    page.getByRole("button", { name: "Chọn chặng Z Foundations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn chặng A Retrieval" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel(/Nguồn đã kiểm chứng/)).toBeChecked();
  await expect(page.getByRole("combobox", { name: "CLO:" })).toHaveValue(
    "CLO1",
  );
  await expect(
    page.getByRole("button", { name: "Chọn chặng Z Foundations" }),
  ).toBeVisible();
  expect(new URL(page.url()).hash).toBe("#roadmap");
  await page.getByLabel(/Nguồn đã kiểm chứng/).uncheck();
  await page.getByLabel(/Local graph/).check();
  await page.getByRole("button", { name: "Chọn chặng A Retrieval" }).click();
  await expect(page.getByRole("dialog")).toContainText("A Retrieval");
  await expect
    .poll(() =>
      api.requested.some((p) => p.includes("/roadmap-nodes/b/graph?depth=2")),
    )
    .toBe(true);
});
test("drag saves layout and survives reload without opening a panel mid-drag", async ({
  page,
}, info) => {
  test.skip(
    info.project.name.includes("mobile"),
    "Pointer and pinch are tested separately on the canvas harness.",
  );
  const api = await backend(page);
  await page.goto("/?kg_roadmap=rm#roadmap");
  const canvas = page.locator("canvas.graph-canvas");
  await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  let rect = (await canvas.boundingBox())!;
  await page.mouse.move(rect.x + 140, rect.y + 140);
  await page.mouse.down();
  await page.mouse.move(rect.x + 200, rect.y + 190, { steps: 5 });
  await page.mouse.up();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect
    .poll(() => api.positions.find((p) => p.node_id === "a")?.pinned)
    .toBe(true);
  const saved = api.positions.find((p) => p.node_id === "a")!;
  await page.reload();
  await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  rect = (await canvas.boundingBox())!;
  await page.mouse.click(rect.x + 60 + saved.x, rect.y + 60 + saved.y);
  await expect(page.getByRole("dialog")).toContainText("Z Foundations");
});

test("search opens the matching panel and milestone scope includes covered prerequisites", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/?kg_roadmap=rm&kg_viewMode=list#roadmap");
  const search = page.getByRole("combobox", { name: /Tìm chặng học/ });
  await expect(search).toBeVisible();
  await search.fill("Retrieval");
  await search.press("Enter");
  await expect(page.getByRole("dialog")).toContainText("A Retrieval");
  await page.getByRole("button", { name: "Xem đồ thị cục bộ" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel(/Local graph/)).toBeChecked();
  await page.getByLabel(/Local graph/).uncheck();
  await search.fill("");
  await page.getByLabel("Tới mốc kiểm tra:").selectOption("exam");
  await expect(
    page.getByRole("button", { name: "Chọn chặng Z Foundations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn chặng A Retrieval" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn chặng Midterm" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn chặng Other topic" }),
  ).toHaveCount(0);
});
test("native touch pinch changes canvas zoom", async ({
  page,
  context,
}, info) => {
  test.skip(
    !info.project.name.includes("mobile"),
    "Touch is exercised at the mobile viewport.",
  );
  await backend(page);
  await page.goto("/?kg_roadmap=rm#roadmap");
  const canvas = page.locator("canvas.graph-canvas");
  await expect(canvas).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  const r = (await canvas.boundingBox())!;
  const cdp = await context.newCDPSession(page);
  const point = (id: number, x: number) => ({
    id,
    x: r.x + x,
    y: r.y + 260,
    radiusX: 2,
    radiusY: 2,
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [point(1, 90), point(2, 170)],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [point(1, 60), point(2, 200)],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await expect(page.locator(".zoom-level")).not.toHaveText("100%");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
for (const layout of ["week", "force"] as const) {
  test(`300-node ${layout} graph pan performance sample`, async ({
    page,
  }, info) => {
    test.skip(
      info.project.name.includes("mobile") ||
        process.env.GRAPH_PERFORMANCE !== "1",
      "Run separately with GRAPH_PERFORMANCE=1 to avoid competing browser workloads.",
    );
    const many = Array.from({ length: 300 }, (_, i) => ({
      ...nodes[0],
      id: "n" + i,
      title: "Topic " + i,
      week: (i % 15) + 1,
    }));
    await backend(page, many);
    await page.goto(`/?kg_roadmap=rm&kg_layout=${layout}#roadmap`);
    const canvas = page.locator("canvas.graph-canvas");
    await expect(canvas).toBeVisible();
    await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
    await canvas.scrollIntoViewIfNeeded();
    const r = (await canvas.boundingBox())!;
    const sample = page.evaluate(
      () =>
        new Promise<{ fps: number; frames: number }>((resolve) => {
          const start = performance.now();
          let frames = 0;
          function step(now: number) {
            frames++;
            if (now - start < 3000) requestAnimationFrame(step);
            else resolve({ fps: (frames * 1000) / (now - start), frames });
          }
          requestAnimationFrame(step);
        }),
    );
    await page.mouse.move(r.x + 20, r.y + 250);
    await page.mouse.down();
    for (let i = 0; i < 90; i++) {
      await page.mouse.move(r.x + 20 + (i % 30) * 5, r.y + 250 + (i % 20));
      await page.waitForTimeout(20);
    }
    await page.mouse.up();
    const result = await sample;
    console.log("GRAPH_PERFORMANCE", layout, JSON.stringify(result));
    await info.attach("graph-performance.json", {
      body: JSON.stringify({
        ...result,
        nodes: 300,
        layout,
        edges: 299,
        environment: "local headless Chrome; no CPU throttling",
      }),
      contentType: "application/json",
    });
    expect(result.fps).toBeGreaterThanOrEqual(50);
  });
}

test("graph list and filters have no serious or critical axe violations", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/?kg_roadmap=rm&kg_viewMode=list#roadmap");
  await expect(
    page.getByRole("button", { name: "Chọn chặng Z Foundations" }),
  ).toBeVisible();
  const result = await new AxeBuilder({ page })
    .include(".kg-filter-bar")
    .include(".kg-list-view-container")
    .analyze();
  expect(
    result.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    ),
  ).toEqual([]);
});

test("approved roadmap edge form adds and removes through the API across reload", async ({
  page,
}) => {
  const api = await backend(page);
  await page.goto("/?kg_roadmap=rm#roadmap");
  await page
    .getByRole("combobox", { name: "Học trước", exact: true })
    .selectOption("c");
  await page
    .getByRole("combobox", { name: "Học sau", exact: true })
    .selectOption("a");
  await page.getByRole("button", { name: "Thêm cạnh", exact: true }).click();
  await expect
    .poll(() => api.requested.some((p) => p.endsWith("/graph/edges")))
    .toBe(true);
  await page.reload();
  const edge = page
    .locator(".core-edge")
    .filter({ hasText: /Other topic.*Z Foundations/ });
  await expect(edge).toBeVisible();
  await edge.getByRole("button", { name: "Bỏ cạnh" }).click();
  await expect(edge).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
  await expect(edge).toHaveCount(0);
});

test("reopened graph restores the syllabus editor and saves to the original course", async ({
  page,
}) => {
  const api = await backend(page);
  await page.goto("/?kg_roadmap=rm#roadmap");
  await expect(page.getByRole("combobox", { name: "CLO:" })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Edit course syllabus" }).click();
  const description = page.locator('input[value="Understand the foundations"]');
  await expect(description).toBeVisible();
  await description.fill("Updated foundations outcome");
  await page
    .getByRole("button", { name: "Xác nhận đề cương", exact: true })
    .click();
  await expect
    .poll(() =>
      api.requested.some((p) =>
        p.endsWith("/courses/c1/syllabus/saved-syllabus"),
      ),
    )
    .toBe(true);
  await page.goto("/?kg_roadmap=rm#roadmap");
  await page.getByRole("button", { name: "Edit course syllabus" }).click();
  await expect(
    page.locator('input[value="Updated foundations outcome"]'),
  ).toBeVisible();
});
test("node gateways open real source details, a private page, and course scheduling", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/?kg_roadmap=rm&kg_viewMode=list#roadmap");
  await page.getByRole("button", { name: "Chọn chặng A Retrieval" }).click();
  await expect(page.getByRole("button", { name: /Hỏi đáp AI/ })).toBeDisabled();
  await page.getByRole("button", { name: "Trang 2 ↗", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Private lecture page two",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Chọn chặng A Retrieval" }).click();
  await page
    .getByRole("button", { name: "Trang chặng (S6)", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("One verified reading");
  await expect(page.getByRole("dialog")).toContainText(
    "Chưa tìm được nguồn đủ tốt",
  );
  await page.getByRole("button", { name: "Mở trang 2", exact: true }).click();
  await expect(page.getByRole("dialog").last()).toContainText(
    "Private lecture page two",
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Xếp lịch lộ trình (S7)", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("toàn bộ lộ trình");
  await expect(page.getByRole("dialog")).toContainText("A Retrieval");
});
test("source labels distinguish private uploads and node path highlight can be cleared", async ({
  page,
}) => {
  await backend(page);
  await page.goto("/?kg_roadmap=rm&kg_viewMode=list#roadmap");
  const privateRow = page.getByRole("row").filter({
    has: page.getByRole("button", { name: "Chọn chặng A Retrieval" }),
  });
  await expect(privateRow).toContainText("0 nguồn đã xác minh");
  await page.getByRole("button", { name: "Chọn chặng A Retrieval" }).click();
  await page.getByRole("button", { name: /Đường học tới đây/ }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Bỏ tô sáng đường học" }),
  ).toBeVisible();
  await expect(page.locator("canvas.graph-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Bỏ tô sáng đường học" }).click();
  await expect(
    page.getByRole("button", { name: "Bỏ tô sáng đường học" }),
  ).toHaveCount(0);
});

test("node panel remains accessible with source metadata and inactive gateways", async ({
  page,
}, info) => {
  if (info.project.name.includes("mobile"))
    await page.setViewportSize({ width: 360, height: 844 });
  await backend(page);
  await page.goto("/?kg_roadmap=rm&kg_viewMode=list#roadmap");
  await page.getByRole("button", { name: "Chọn chặng Z Foundations" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Massachusetts Institute of Technology",
  );
  const result = await new AxeBuilder({ page })
    .include(".node-panel-container")
    .analyze();
  expect(
    result.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
  ).toEqual([]);
  await page.emulateMedia({ colorScheme: "dark" });
  // Audit settled theme colors, not intermediate frames of the color transition.
  await page.locator(".node-panel-container").evaluate(async (panel) => {
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => resolve()),
    );
    const finite = panel
      .getAnimations({ subtree: true })
      .filter((animation) =>
        Number.isFinite(
          animation.effect?.getComputedTiming().endTime ?? Infinity,
        ),
      );
    await Promise.all(
      finite.map((animation) => animation.finished.catch(() => undefined)),
    );
  });
  const dark = await new AxeBuilder({ page })
    .include(".node-panel-container")
    .analyze();
  expect(
    dark.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
  ).toEqual([]);
  await page
    .getByRole("button", { name: "Trang chặng (S6)", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("One verified reading");
  const sources = await new AxeBuilder({ page }).include("dialog").analyze();
  expect(
    sources.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
  ).toEqual([]);
});
