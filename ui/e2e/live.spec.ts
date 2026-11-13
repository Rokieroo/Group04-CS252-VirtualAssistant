import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The real app (VITE_BACKEND_MODE=api) against intercepted API responses. This checks that
// the screens send and read the wire format in docs/openapi.json; it is not a test of the server.
const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const step = (id: string, title: string, week: number, extra = {}) => ({
  id,
  roadmap_id: "rm1",
  type: "topic",
  kind: "topic",
  title,
  week,
  duration_minutes: 90,
  est_minutes: 90,
  due_at: null,
  covers: [],
  ...extra,
});
const roadmap = {
  id: "rm1",
  roadmap_id: "rm1",
  course_id: "c1",
  user_id: "u1",
  title: "CSC10014",
  created_at: ago(9000),
  nodes: [
    step("n1", "Phân rã bài toán", 1, { status: "done" }),
    step("n2", "Thiết kế thuật toán", 2),
    step("m1", "Giữa kỳ", 2, { type: "milestone", kind: "milestone", covers: ["n1", "n2"] }),
  ],
};
const sources = {
  node_id: "n2",
  status: "ready",
  user_material_count: 1,
  sources: [
    {
      kind: "user_material",
      id: "s1",
      source_id: "s1",
      title: "Tuan2.pdf",
      url: null,
      pages: [3, 4],
      provider: "upload",
      format: "slides",
      reason: "Tài liệu của bạn",
    },
    {
      kind: "catalog",
      id: "r1",
      title: "Thiết kế thuật toán (MIT OCW)",
      url: "https://ocw.mit.edu/x",
      pages: [],
      provider: "MIT OpenCourseWare",
      institution: "MIT",
      license: "CC-BY-NC-SA-4.0",
      format: "course",
      reason: "Khớp chủ đề của bước",
      verification_status: "verified",
    },
    {
      kind: "external",
      id: "x1",
      title: "Greedy algorithms explained",
      url: "https://example.net/greedy",
      pages: [],
      provider: "example.net",
      format: "video",
      reason: "Ví dụ trực quan",
      verification_status: "verified",
    },
  ],
};
const web = {
  status: "ready",
  gaps: [],
  resources: [
    {
      id: "w1",
      rank: 1,
      title: "Algorithm design basics",
      url: "https://example.org/a",
      domain: "example.org",
      format: "article",
      language: "en",
      duration_min: 20,
      is_free: true,
      score: 0.8,
      breakdown: {},
      reason: "Giải thích rõ từng bước",
      evidence_quote: "",
      pinned: false,
    },
  ],
};
const queue = {
  resources: [
    {
      id: "q1",
      title: "Open Data Structures",
      url: "https://opendatastructures.org",
      provider: "manual",
      license: null,
      verification_status: "pending",
      checks: [{ check: "license", result: "review", reason: "license_unknown", checked_at: ago(60) }],
    },
  ],
};

type Sent = { key: string; body: unknown };

/** Answers every API call from fixtures and records what the UI sent. */
async function backend(page: Page, options: { role?: string; signedIn?: boolean; loginStatus?: number } = {}) {
  const sent: Sent[] = [];
  let entryStatus = "planned";
  await page.addInitScript((signedIn) => {
    if (signedIn) sessionStorage.setItem("pathly.session", "test-token");
    localStorage.setItem("pathly.course", JSON.stringify({ roadmapId: "rm1" }));
  }, options.signedIn ?? true);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const key = `${request.method()} ${new URL(request.url()).pathname.replace("/api/v1", "")}`;
    const body = request.headers()["content-type"]?.includes("json") ? request.postDataJSON() : null;
    sent.push({ key, body });
    const answers: Record<string, unknown> = {
      "GET /me": {
        id: "u1",
        name: "Minh",
        email: "minh@example.test",
        timezone: "Asia/Ho_Chi_Minh",
        personality: "warm",
        role: options.role ?? "student",
        account_level: "university",
        birth_year: 2005,
        companion_mode: "buddy",
      },
      "GET /notifications": [{ id: "nt1", message: "Buổi học bắt đầu sau 15 phút.", read: false, entry_id: "e1" }],
      "GET /roadmaps/rm1": roadmap,
      "GET /roadmaps/rm1/edges": [
        { parent_id: "n1", child_id: "n2", kind: "strict", confidence: 1, origin: "llm" },
      ],
      "GET /concepts/n2/sources": sources,
      "GET /roadmap-nodes/n2/materials": { files: [] },
      "GET /roadmap-nodes/n2/resources": web,
      "GET /roadmap-nodes/n2/exercises": { node_id: "n2", count: 0, exercises: [] },
      "POST /resources/w1/feedback": { status: "ok", replacement: null },
      "GET /tasks": [{ id: "t1", title: "Thiết kế thuật toán" }],
      "GET /schedule": [
        { id: "e1", task_id: "t1", starts_at: ago(90), ends_at: ago(30), status: entryStatus, actual_minutes: 0 },
      ],
      "GET /reports/weekly": {
        total_tasks: 3,
        completed_tasks: 1,
        planned_minutes: 270,
        completed_minutes: 90,
        missed_sessions: 0,
        completion_percent: 33,
        start_date: "2026-11-09",
        end_date: "2026-11-15",
      },
      "GET /reviews/due": [
        {
          item_id: "i1",
          user_id: "u1",
          node_id: "n1",
          due_at: ago(60),
          stability: 1,
          difficulty: 5,
          state: 2,
          step: 0,
          prompt: "Phân rã bài toán là gì?",
          choices: null,
          type: "short",
        },
      ],
      "POST /reviews/i1": {},
      "GET /admin/catalog/review-queue": queue,
      "POST /admin/catalog/resources/q1:verify": { id: "q1", verification_status: "verified", license: null },
      "POST /auth/login": { access_token: "test-token" },
    };
    if (key === "POST /schedule/e1/check-in") entryStatus = "completed";
    if (key === "POST /auth/login" && options.loginStatus)
      return route.fulfill({ status: options.loginStatus, json: { detail: "Invalid email or password" } });
    if (key === "GET /courses/c1/syllabus") return route.fulfill({ status: 404, json: { detail: "not_found" } });
    return route.fulfill({ json: answers[key] ?? (request.method() === "GET" ? [] : {}) });
  });
  return sent;
}

const accessible = async (page: Page) =>
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

test("signing in reopens the approved roadmap with its progress", async ({ page }) => {
  await backend(page, { signedIn: false });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Đăng nhập" })).toBeVisible();
  await accessible(page);
  await page.getByLabel("Email").fill("minh@example.test");
  await page.getByLabel("Mật khẩu").fill("mat-khau-thu");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByText("1/2 bước đã xong")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tiếp theo: tuần 2" })).toBeVisible();
  await accessible(page);
});

test("a due review card is rated and the next one takes its place", async ({ page }) => {
  const sent = await backend(page);
  await page.goto("/");
  await expect(page.getByText("Phân rã bài toán là gì?")).toBeVisible();
  await accessible(page);
  await page.getByRole("button", { name: "Được" }).click();
  await expect(page.getByRole("heading", { name: "Ôn tập đến hạn" })).toHaveCount(0);
  expect(sent.find((s) => s.key === "POST /reviews/i1")?.body).toEqual({ rating: 3, node_id: "n1" });
});

test("a wrong password says so instead of talking about sessions", async ({ page }) => {
  await backend(page, { signedIn: false, loginStatus: 401 });
  await page.goto("/");
  await page.getByLabel("Email").fill("minh@example.test");
  await page.getByLabel("Mật khẩu").fill("sai-mat-khau");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email hoặc mật khẩu không đúng.");
});

test("a step lists own pages, verified sources and web results, in that order of trust", async ({ page }) => {
  const sent = await backend(page);
  await page.goto("/#roadmap");
  await page.getByRole("button", { name: /Thiết kế thuật toán/ }).click();
  const panel = page.getByRole("region", { name: "Chi tiết: Thiết kế thuật toán" });
  await expect(panel.getByText("Tuan2.pdf")).toBeVisible();
  await expect(panel.getByRole("button", { name: "tr. 3" })).toBeVisible();
  // Only the catalog source carries the verified badge; external and web results never do,
  // even when the server marks them verified.
  await expect(panel.getByRole("link", { name: /Greedy algorithms explained/ })).toBeVisible();
  await expect(panel.getByText("Đã kiểm chứng", { exact: true })).toHaveCount(1);
  await expect(panel.getByRole("link", { name: /Algorithm design basics/ })).toBeVisible();
  await accessible(page);

  await panel.getByRole("button", { name: "Hữu ích" }).click();
  await expect(panel.getByText("Đã ghi nhận đánh giá của bạn.")).toBeVisible();
  expect(sent.find((s) => s.key === "POST /resources/w1/feedback")?.body).toEqual({
    node_id: "n2",
    helpful: true,
  });
});

test("a past session is checked in with the minutes studied", async ({ page }) => {
  const sent = await backend(page);
  await page.goto("/#schedule");
  await expect(page.getByText("Thiết kế thuật toán")).toBeVisible();
  await accessible(page);
  await page.getByRole("button", { name: "Đã học" }).click();
  await expect(page.getByRole("listitem").getByText("Đã học", { exact: true })).toBeVisible();
  expect(sent.find((s) => s.key === "POST /schedule/e1/check-in")?.body).toEqual({
    status: "completed",
    actual_minutes: 60,
  });
});

test("an admin verifies the open source from the keyboard", async ({ page }) => {
  const sent = await backend(page, { role: "admin" });
  await page.goto("/#admin");
  await expect(page.getByRole("heading", { name: "Open Data Structures" })).toBeVisible();
  await accessible(page);
  await page.keyboard.press("v");
  await expect(page.getByText("Đã duyệt: Open Data Structures")).toBeVisible();
  expect(sent.find((s) => s.key === "POST /admin/catalog/resources/q1:verify")?.body).toEqual({
    reason: "Footer confirms CC-BY-4.0",
    license: null,
  });
});

test("the admin screen stays closed to a learner", async ({ page }) => {
  await backend(page);
  await page.goto("/#admin");
  await expect(page.getByText("1/2 bước đã xong")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quản trị" })).toHaveCount(0);
});
