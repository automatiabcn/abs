// The scenario suite: one config, one browser, a real backend.
//
// Separate from playwright.config.ts on purpose. That suite is about surfaces —
// does the route render, is it accessible, does it survive an offline blip —
// and it mocks the network to stay fast and deterministic. This one is about
// whether the product works: a person signs in, asks a question, gets an
// answer, approves an action, uploads a recording. It is slower, it needs the
// backend up, and it must not be mixed into the fast suite where its failures
// would read as flakes.
//
//   cd core/backend && ./.localrun/run_backend.sh   # :8000
//   cd core/landing && npx playwright test -c playwright.scenarios.config.ts
//
// One browser (Chromium): these scenarios exercise the server, and running the
// same server conversation three times through three engines buys nothing.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./__tests__/scenarios",
  // Serial: the scenarios share one backend, one database and one quota. Two
  // of them approving actions in parallel would be testing the test harness.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // No retries. A scenario that passes on the second try is a scenario that
  // failed, and the whole reason this suite exists is to stop believing
  // green that was never earned.
  retries: 0,
  // A real cascade call can take a while, and a slow answer is still an answer.
  timeout: 180_000,
  expect: { timeout: 30_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report-scenarios" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3458",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    // One sign-in for the whole suite. Per-test logins hit the (correct)
    // 5/minute brute-force cap and failed whichever scenario came sixth.
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: "playwright/.auth/admin.json" },
    },
  ],
  // Point PLAYWRIGHT_BASE_URL at a dev server you already have running and the
  // suite uses it instead of starting its own. Two `next dev` processes in one
  // checkout share (and corrupt) the .next cache, which shows up as a login page
  // that never hydrates — a failure that looks like the product's fault and
  // isn't.
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        // The landing proxies /v1/* to ABS_BACKEND_URL, so the browser talks to
        // the real API through the real front door.
        command: "npx next dev --port 3458 --hostname 127.0.0.1",
        url: "http://127.0.0.1:3458/login",
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
        env: {
          ABS_BACKEND_URL: process.env.ABS_BACKEND_URL ?? "http://127.0.0.1:8000",
        },
      },
});
