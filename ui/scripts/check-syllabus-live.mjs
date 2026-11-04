import {fileURLToPath} from "node:url";
// Run from ui: node scripts/check-syllabus-live.mjs. Uses an isolated in-memory backend.
import { spawn } from "node:child_process";
import { existsSync, readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as pause } from "node:timers/promises";
import { chromium, expect } from "@playwright/test";
process.chdir(fileURLToPath(new URL("..", import.meta.url)));
const python =
  process.env.SYLLABUS_TEST_PYTHON ||
  (process.platform === "win32"
    ? "../.venv/Scripts/python.exe"
    : "../.venv/bin/python");
if (!existsSync(python) && !process.env.SYLLABUS_TEST_PYTHON)
  throw Error(
    "Activate/install the project Python environment, or set SYLLABUS_TEST_PYTHON.",
  );
const children = [];
let browser;
let logs = "";
function start(exe, args, env = process.env) {
  const child = spawn(exe, args, {
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (x) => (logs += x));
  child.stderr.on("data", (x) => (logs += x));
  child.on("error", (e) => (logs += e.message));
  children.push(child);
  return child;
}
async function wait(url) {
  for (let i = 0; i < 100; i++) {
    if (children.some((p) => p.exitCode !== null)) throw Error(logs);
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await pause(150);
  }
  throw Error("Server timeout: " + logs);
}
try {
  start(python, ["scripts/syllabus-test-server.py"]);
  start(
    process.execPath,
    [
      "node_modules/vite/bin/vite.js",
      "--host",
      "127.0.0.1",
      "--port",
      "5182",
      "--strictPort",
    ],
    {
      ...process.env,
      VITE_BACKEND_MODE: "api",
      VITE_API_URL: "http://127.0.0.1:8012",
    },
  );
  await wait("http://127.0.0.1:8012/api/v1/health");
  await wait("http://127.0.0.1:5182");
  const registration = await fetch(
    "http://127.0.0.1:8012/api/v1/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Syllabus test",
        email: "syllabus-test@example.test",
        password: "test-password-123",
        birth_year: 2004,
      }),
    },
  );
  expect(registration.status).toBe(201);
  const token = (await registration.json()).access_token;
  browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    headless: true,
  });
  mkdirSync("../docs/screenshots/56", { recursive: true });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    const page = await browser.newPage({
      viewport,
      reducedMotion: "reduce",
      colorScheme: "light",
    });
    await page.addInitScript(
      (token) => sessionStorage.setItem("pathly.session", token),
      token,
    );
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const format of ["pdf", "docx", "text"]) {
      await page.goto("http://127.0.0.1:5182");
      await expect(
        page.getByRole("heading", { name: "Course details", exact: true }),
      ).toBeVisible();
      if (format === "text") {
        await page.getByRole("button", { name: "Prefer text?" }).click();
        await page
          .getByRole("textbox", { name: "Syllabus text" })
          .fill(
            readFileSync(
              "../eval/syllabus/01_csc10014_problem_framing.txt",
              "utf8",
            ),
          );
      } else
        await page
          .getByLabel("Syllabus file", { exact: true })
          .setInputFiles(
            resolve(
              format === "pdf"
                ? "../eval/syllabus/01_csc10014_problem_framing.pdf"
                : ".tmp/CSC10014.docx",
            ),
          );
      await page.getByRole("button", { name: "Continue to review" }).click();
      await expect(
        page.getByRole("heading", {
          name: "Review your syllabus",
          exact: true,
        }),
      ).toBeVisible({ timeout: 20000 });
      await expect(
        page.getByLabel("Mã CLO", { exact: true }).first(),
      ).toHaveValue("CLO1");
      const citation = page.getByRole("button", { name: /^tr\. \d/ }).first();
      await citation.click();
      await expect(page.getByRole("dialog")).toContainText("CLO1");
      await page.keyboard.press("Escape");
      await expect(citation).toBeFocused();
      await page
        .getByRole("tab", { name: "Tuần & chủ đề", exact: true })
        .click();
      await expect(page.getByLabel("Tuần", { exact: true })).toHaveCount(10);
      await page.getByRole("tab", { name: "Giáo trình", exact: true }).click();
      await page
        .getByRole("button", { name: "+ Thêm giáo trình", exact: true })
        .click();
      await page
        .getByLabel("Tên giáo trình", { exact: true })
        .last()
        .fill("Reviewed CSC10014 notes");
      await page
        .getByLabel("Tác giả", { exact: true })
        .last()
        .fill("Course staff");
      await page.getByRole("tab", { name: "Đánh giá", exact: true }).click();
      const weight = page.getByLabel("Trọng số %", { exact: true }).first();
      const original = await weight.inputValue();
      await weight.fill("0");
      await expect(
        page.getByRole("button", { name: "Xác nhận đề cương", exact: true }),
      ).toBeDisabled();
      await weight.fill(original);
      await expect(
        page.getByRole("button", { name: "Xác nhận đề cương", exact: true }),
      ).toBeEnabled();
      await page
        .getByRole("button", { name: "Xác nhận đề cương", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Đã xác nhận", exact: true }),
      ).toBeVisible();
      const headers = { Authorization: "Bearer " + token };
      const courses = await (
        await fetch("http://127.0.0.1:8012/api/v1/courses", { headers })
      ).json();
      const saved = await (
        await fetch(
          "http://127.0.0.1:8012/api/v1/courses/" + courses[0].id + "/syllabus",
          { headers },
        )
      ).json();
      const parsed = JSON.parse(saved.raw_text);
      expect(parsed.weeks).toHaveLength(10);
      expect(parsed.textbooks.at(-1).title).toBe("Reviewed CSC10014 notes");
      expect(Object.keys(parsed.source_pages).length).toBeGreaterThan(0);
      expect(saved.assessments.reduce((n, a) => n + a.weight, 0)).toBe(100);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
      if (format === "pdf") {
        await page.evaluate(() => {
          document.activeElement?.blur();
          window.scrollTo(0, 0);
        });
        await page.screenshot({
          path: `../docs/screenshots/56/live-review-${viewport.width}.png`,
          fullPage: true,
        });
      }
      console.log(
        `${viewport.width}x${viewport.height} ${format}: real upload/parse, citations, four tabs, corrections and persisted confirmation passed`,
      );
    }
    await page.close();
  }
} catch (error) {
  console.error(logs);
  throw error;
} finally {
  await browser?.close();
  for (const child of children) child.kill();
}
