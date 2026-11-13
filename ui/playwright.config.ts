import { defineConfig, devices } from "@playwright/test";

const PREVIEW = "http://127.0.0.1:5178";
const LIVE = "http://127.0.0.1:5180";
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } };
const phone = { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    channel: process.env.PLAYWRIGHT_CHANNEL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "preview", testMatch: /preview\.spec\.ts/, use: { ...desktop, baseURL: PREVIEW } },
    { name: "preview-mobile", testMatch: /preview\.spec\.ts/, use: { ...phone, baseURL: PREVIEW } },
    { name: "live", testMatch: /live\.spec\.ts/, use: { ...desktop, baseURL: LIVE } },
    { name: "live-mobile", testMatch: /live\.spec\.ts/, use: { ...phone, baseURL: LIVE } },
  ],
  webServer: [
    {
      command: "npx --no-install vite --host 127.0.0.1 --port 5178 --strictPort",
      url: PREVIEW,
      reuseExistingServer: false,
      // Explicit modes: a developer's ui/.env.local must not switch the suites.
      env: { VITE_BACKEND_MODE: "demo", VITE_CACHE_DIR: "node_modules/.vite-e2e-preview" },
    },
    {
      command: "npx --no-install vite --host 127.0.0.1 --port 5180 --strictPort",
      url: LIVE,
      reuseExistingServer: false,
      // The live spec answers every /api/v1 call with page.route, so no server runs behind it.
      env: {
        VITE_BACKEND_MODE: "api",
        VITE_API_URL: LIVE,
        VITE_CACHE_DIR: "node_modules/.vite-e2e-live",
      },
    },
  ],
});
