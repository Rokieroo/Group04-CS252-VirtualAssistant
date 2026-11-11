import { test, expect } from "@playwright/test";

test("root paths keep recalculated radial zones during pointer dragging and preserve details", async ({
  page,
}) => {
  await page.goto("/e2e/fixtures/root-layout.html");
  const paths = page.locator("[data-course-path]");
  await expect(paths).toHaveCount(3);
  const node = paths.first().locator(".root-node").nth(1);
  await node.scrollIntoViewIfNeeded();
  const before = await node.getAttribute("data-radius");
  const box = (await node.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(-100, -100, { steps: 8 });
  await page.mouse.up();
  await expect(node).not.toHaveAttribute("data-radius", before!);
  await expect(page.getByRole("dialog")).toContainText(
    "Checkpoint 2 description",
  );
  await page
    .getByRole("button", { name: "Close description", exact: true })
    .click();
  const check = async () => {
    const lanes = await paths.evaluateAll((groups) =>
      groups.map((g) =>
        [...g.querySelectorAll(".root-node")].map((n) => ({
          r: Number(n.getAttribute("data-radius")),
          low: Number(n.getAttribute("data-low-radius")),
          high: Number(n.getAttribute("data-high-radius")),
        })),
      ),
    );
    for (const nodes of lanes)
      for (let i = 0; i < nodes.length; i++) {
        expect(nodes[i].r - 15).toBeGreaterThan(nodes[i].low);
        expect(nodes[i].r + 15).toBeLessThan(nodes[i].high);
        if (i) expect(nodes[i].low).toBeGreaterThan(nodes[i - 1].high);
      }
  };
  await check();
  await page.getByRole("button", { name: "Change checkpoint counts" }).click();
  await expect(paths.first().locator(".root-node")).toHaveCount(12);
  await check();
  await page.getByRole("button", { name: "Show geometry" }).click();
  await expect(
    page.getByRole("button", { name: "Hide geometry" }),
  ).toBeVisible();
  await page
    .locator(".root-svg")
    .screenshot({ path: test.info().outputPath("root-zones.png") });
  const target = paths.last().locator(".root-node").first();
  await target.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText(
    "Checkpoint 1 description",
  );
});
