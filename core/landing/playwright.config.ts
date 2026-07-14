// Playwright config for the ABS landing routes.
// Boots `next dev` on port 3457 and runs the suites under __tests__/playwright/.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./__tests__/playwright",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3457",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "chromium-mobile", use: { ...devices["Pixel 7"] } },
    // cross-browser smoke surface. Run with
    // `--project=firefox-desktop` or `webkit-desktop` to exercise
    // engine-specific routing/SSR quirks.
    { name: "firefox-desktop", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit-desktop", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: "npx next dev --port 3457",
    url: "http://localhost:3457",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
