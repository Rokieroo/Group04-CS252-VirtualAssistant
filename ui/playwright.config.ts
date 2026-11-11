import { defineConfig, devices } from "@playwright/test";

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
    {
      name: "desktop-demo",
      testMatch: /demo\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        baseURL: "http://127.0.0.1:5178",
      },
    },
    {
      name: "mobile-demo",
      testMatch: /demo\.spec\.ts/,
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 844 },
        baseURL: "http://127.0.0.1:5178",
      },
    },
    {
      name: "api-contract",
      testMatch: /api\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:5179" },
    },
    {
      name: "backend-ui",
      testMatch: /(concepts|syllabus|graph|courses|root)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:5180" },
    },
    {
      name: "backend-ui-mobile",
      testMatch: /(syllabus|graph|courses|root)\.spec\.ts/,
      use: {
        ...devices["Pixel 7"],
        viewport: { width: 390, height: 844 },
        baseURL: "http://127.0.0.1:5180",
      },
    },
  ],
  webServer: [
    {
      command:
        "npx --no-install vite --host 127.0.0.1 --port 5178 --strictPort",
      url: "http://127.0.0.1:5178",
      reuseExistingServer: false,
      // Explicit modes: a developer's ui/.env.local must not switch the suites.
      env: {
        VITE_CHECK_MODE: "demo",
        VITE_BACKEND_MODE: "legacy-demo",
        VITE_CACHE_DIR: "node_modules/.vite-e2e-demo",
      },
    },
    {
      command:
        "npx --no-install vite --host 127.0.0.1 --port 5179 --strictPort",
      url: "http://127.0.0.1:5179",
      reuseExistingServer: false,
      env: {
        VITE_CHECK_MODE: "api",
        VITE_API_BASE_URL: "http://127.0.0.1:5179/api/v1",
        VITE_BACKEND_MODE: "legacy-demo",
        VITE_CACHE_DIR: "node_modules/.vite-e2e-api",
      },
    },
    {
      command:
        "npx --no-install vite --host 127.0.0.1 --port 5180 --strictPort",
      url: "http://127.0.0.1:5180",
      reuseExistingServer: false,
      env: {
        VITE_BACKEND_MODE: "api",
        VITE_API_URL: "http://127.0.0.1:5180",
        VITE_CACHE_DIR: "node_modules/.vite-e2e-backend",
      },
    },
  ],
});
