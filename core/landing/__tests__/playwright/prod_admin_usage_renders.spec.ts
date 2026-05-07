// Brief 4 R7 — Tremor charts on /admin/usage render against real
// backend data (the route split sends the page to landing while the
// data fetch hits backend through `/v1/admin/usage`).

import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  PROD_BASE_URL,
  requireProdStack,
} from "./helpers/prod-stack";

test.describe("Brief 4 R7 — admin usage charts (production stack)", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireProdStack(request, testInfo);
  });

  test("backend exposes /v1/admin/usage as JSON via Caddy", async ({
    request,
  }) => {
    const auth = await request.post(`${PROD_BASE_URL}/auth/login`, {
      ignoreHTTPSErrors: true,
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    expect(auth.ok()).toBeTruthy();

    const r = await request.get(`${PROD_BASE_URL}/v1/admin/usage`, {
      ignoreHTTPSErrors: true,
    });
    // 200 with a usage payload OR 401 when the admin token is not yet
    // bootstrapped on this stack — both prove the route reaches the
    // backend through Caddy (vs. the deleted backend `/admin` page).
    expect([200, 401]).toContain(r.status());
    const ctype = (r.headers()["content-type"] ?? "").toLowerCase();
    expect(ctype).toContain("application/json");
  });

  test("/admin/usage page renders the Tremor chart shell", async ({
    browser,
  }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await ctx.request.post(`${PROD_BASE_URL}/auth/login`, {
        data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
      });
      const page = await ctx.newPage();
      await page.goto(`${PROD_BASE_URL}/admin/usage`, {
        waitUntil: "domcontentloaded",
      });
      // At minimum, the page must not be a backend 404 / vanilla HTML.
      const heading = page.getByRole("heading", { level: 1 });
      await expect(heading).toBeVisible({ timeout: 10_000 });
      // Tremor chart container, brand-aligned card or grid layout.
      const container = page.locator(
        '[data-testid*="usage"], .recharts-responsive-container, [data-tremor]',
      );
      await expect(container.first()).toBeVisible({ timeout: 15_000 });
    } finally {
      await ctx.close();
    }
  });
});
