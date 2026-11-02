import { expect, type Page } from "@playwright/test";

export async function signIn(page: Page) {
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("student@example.test");
  await page.getByLabel("Password", { exact: true }).fill("demo-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

export async function navigate(page: Page, name: string) {
  const mobile = page.getByRole("navigation", {
    name: "Main navigation (mobile)",
    exact: true,
  });
  const navigation = (await mobile.isVisible())
    ? mobile
    : page.getByRole("navigation", { name: "Main navigation", exact: true });
  await navigation.getByRole("button", { name, exact: true }).click();
}

/** Mastery opens from a course goal in the sidebar (behind the menu button on phones). */
export async function openGoal(page: Page, course: string) {
  const menu = page.getByRole("button", { name: "Toggle navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .locator(".goals")
    .getByRole("button", { name: new RegExp(course) })
    .click();
}
