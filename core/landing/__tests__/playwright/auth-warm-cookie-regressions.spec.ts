// Regression suite for 3 bugs + page-title sweep surfaced by a headed
// Playwright walkthrough.
//
//   BUG-1  HIGH  /login submit must land on /panel
//   BUG-2  HIGH  /admin/marketplace must render under 5s (warm)
//   BUG-3  MED   chat send button must expose aria-label + data-testid
//   SWEEP        every panel/admin route must ship a unique <title>
//
// The suite logs in once via API (so per-test cookies are warm) and
// reuses storage state — much faster than driving the form per test
// while still proving the redirect contract in BUG-1.

import { expect, test, type Page } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3457";
const ADMIN = { email: "admin@demo-acme.com", password: "DemoPass2026!" };

async function apiLogin(page: Page) {
  // Hit the rewrite directly so the abs_session cookie lands on the
  // landing origin Playwright drives.
  const res = await page.request.post(`${BASE}/auth/login`, {
    data: ADMIN,
    headers: { "Content-Type": "application/json" },
  });
  expect(res.ok()).toBeTruthy();
}

test.describe("login redirect (BUG-1)", () => {
  test("login form lands on /panel within 10s", async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    // Wait for React hydration; the submit button is gated on it so a
    // fast click can't trigger a native GET form submit to /login?.
    await expect(page.locator('form[data-hydrated="true"]')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator('[data-testid="login-submit"]')).toBeEnabled();
    await page.locator('input[type="email"]').fill(ADMIN.email);
    await page.locator('input[type="password"]').fill(ADMIN.password);
    await Promise.all([
      page.waitForURL(/\/panel(\b|\/)/, { timeout: 10_000 }),
      page.locator('[data-testid="login-submit"]').click(),
    ]);
    expect(page.url()).toMatch(/\/panel(\b|\/)/);
  });
});

test.describe("marketplace render (BUG-2)", () => {
  test("/admin/marketplace renders within 5s warm", async ({ page }) => {
    await apiLogin(page);
    // First visit warms the dev compile cache; second visit is the budget.
    await page.goto(`${BASE}/admin/marketplace`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    const t0 = Date.now();
    await page.goto(`${BASE}/admin/marketplace`, {
      waitUntil: "domcontentloaded",
      timeout: 5_000,
    });
    expect(Date.now() - t0).toBeLessThan(5_000);
    await expect(page.locator("h1")).toContainText(/Plugin Marketplace/i);
  });
});

test.describe("chat send button a11y (BUG-3)", () => {
  test("send button exposes aria-label + data-testid", async ({ page }) => {
    await apiLogin(page);
    await page.goto(`${BASE}/panel/chat`, { waitUntil: "domcontentloaded" });
    const send = page.locator('[data-testid="chat-send"]');
    await expect(send).toBeVisible({ timeout: 15_000 });
    await expect(send).toHaveAttribute("aria-label", /gönder|send|enviar/i);
  });
});

test.describe("page title sweep", () => {
  const TITLES: Array<[string, RegExp]> = [
    ["/panel", /Overview — ABS Panel/],
    ["/panel/chat", /Sohbet — ABS Panel/],
    ["/panel/tools", /MCP Tool Browser — ABS Panel/],
    ["/panel/quota", /Usage — ABS Panel/],
    ["/panel/meetings", /Meetings — ABS Panel/],
    ["/panel/transcription", /Live Transcription — ABS Panel/],
    ["/admin/settings", /Settings — ABS Admin/],
    ["/admin/providers", /Providers — ABS Admin/],
    ["/admin/marketplace", /Plugin Marketplace — ABS Admin/],
    ["/admin/workflow-builder", /Workflow Builder — ABS Admin/],
    ["/admin/pipelines", /Quality Pipelines — ABS Admin/],
    ["/admin/rag", /Knowledge Base — ABS Admin/],
    ["/admin/audit", /Audit — ABS Admin/],
    ["/admin/users", /Users — ABS Admin/],
    ["/admin/graph", /Knowledge Graph — ABS Admin/],
  ];

  for (const [path, expected] of TITLES) {
    test(`${path} ships unique title`, async ({ page }) => {
      await apiLogin(page);
      await page.goto(`${BASE}${path}`, {
        waitUntil: "domcontentloaded",
        timeout: 30_000,
      });
      await expect(page).toHaveTitle(expected);
    });
  }
});
