// Re-render docs/wireframes/img/*.png from index.html. Run from the repo root after `python dev.py ui install`:
//   node docs/wireframes/capture.mjs
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(new URL("../../ui/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const pageUrl = new URL("index.html", import.meta.url).href;
const out = fileURLToPath(new URL("img/", import.meta.url));
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pageUrl);
const frames = await page.evaluate(() => window.FRAMES);
for (const [id, , , size] of frames) {
  await page.setViewportSize(size === "d" ? { width: 1440, height: 900 } : { width: 390, height: 844 });
  await page.goto(`${pageUrl}?frame=${id}`);
  await page.screenshot({ path: `${out}${id}.png` });
}
for (const section of ["flows", "components"]) {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(`${pageUrl}?section=${section}`);
  await page.screenshot({ path: `${out}${section}.png`, fullPage: true });
}
await browser.close();
console.log(`${frames.length + 2} images in ${out}`);
