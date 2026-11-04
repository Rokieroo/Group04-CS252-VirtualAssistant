import { expect, test, type Page, type Route } from "@playwright/test";
import { navigate } from "./helpers";

// The UI in VITE_BACKEND_MODE=api; the backend is answered here, so no server or LLM runs.
const concepts = [
  { id: "c1", slug: "solution-ladder", title: "Solution ladder", summary: "Leo tới bậc thấp nhất đủ dùng.", bloom_level: "understand", source_pages: [2, 3], confirmed: false },
  { id: "c2", slug: "framing-ladder", title: "Framing ladder", summary: "Need → Problem → Split → Options → Success.", bloom_level: "apply", source_pages: [5], confirmed: false },
];

async function backend(page: Page, propose: (route: Route) => Promise<void>) {
  const requests: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname + new URL(request.url()).search;
    requests.push(`${request.method()} ${path}`);
    if (path.endsWith("/auth/register"))
      return route.fulfill({ status: 201, json: { access_token: "tok" } });
    if (path.endsWith("/courses") && request.method() === "GET") return route.fulfill({ json: [] });
    if (path.endsWith("/courses")) return route.fulfill({ status: 201, json: { id: "course-1" } });
    if (path.endsWith("/sources"))
      return route.fulfill({
        status: 201,
        json: { file_name: "week01.pdf", pages: 6, status: "processed", warning: null },
      });
    if (path.includes("concepts:propose")) return propose(route);
    return route.fulfill({ status: 500, json: { detail: "unexpected" } });
  });
  return requests;
}

async function registerAndUpload(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /No account yet/ }).click();
  await page.getByLabel("Email", { exact: true }).fill("student@example.test");
  await page.getByLabel("Password", { exact: true }).fill("pass-1234");
  await page.getByLabel("Birth year", { exact: true }).fill("2005");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
  await navigate(page, "Courses");
  await page.getByLabel("Choose PDF files to upload").setInputFiles({
    name: "week01.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n%%EOF"),
  });
}

test("uploaded PDF is extracted by the backend and its concepts are listed", async ({ page }) => {
  const requests = await backend(page, (route) =>
    route.fulfill({ json: { concepts, prereqs: [] } }),
  );
  await registerAndUpload(page);
  await expect(page.locator(".file-list .processed")).toContainText("6 pages");
  await expect(page.locator(".concept-list > li")).toHaveCount(2);
  await expect(page.getByRole("textbox", { name: "Rename Solution ladder" })).toBeVisible();
  await expect(page.locator(".concept-list")).toContainText("p. 2, 3");
  expect(requests).toContain("POST /api/v1/courses/course-1/concepts:propose?file_name=week01.pdf");
});

test("a failed extraction keeps the upload and explains why", async ({ page }) => {
  await backend(page, (route) =>
    route.fulfill({ status: 503, json: { detail: "concepts_unavailable" } }),
  );
  await registerAndUpload(page);
  await expect(page.locator(".file-list .processed")).toContainText("6 pages");
  await expect(page.getByRole("alert")).toContainText("could not read this file right now");
  await expect(page.locator(".concept-list > li")).toHaveCount(0);
});
