// Brief 4 R7 — `/admin/login` works against the production stack.
//
// Verifies:
//   1. Unauthenticated `/admin/dashboard` visit redirects to /admin/login
//      (landing middleware path).
//   2. POST /auth/login (backend, via Caddy) sets the session cookie on
//      the shared abs.local origin so the Next.js admin can read it.
//   3. After login, /admin/dashboard renders without a redirect.

import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  COOKIE_NAME,
  PROD_BASE_URL,
  loginThroughCaddy,
  requireProdStack,
} from "./helpers/prod-stack";

test.describe("Brief 4 R7 — Next.js admin login (production stack)", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireProdStack(request, testInfo);
  });

  test("guest hitting /admin/dashboard is redirected to /admin/login", async ({
    request,
  }) => {
    const r = await request.get(`${PROD_BASE_URL}/admin/dashboard`, {
      ignoreHTTPSErrors: true,
      maxRedirects: 0,
    });
    // Next.js middleware emits 307 (default) or 302; both map to the
    // same intent: forbid anonymous access.
    expect([302, 307]).toContain(r.status());
    const loc = r.headers()["location"] ?? "";
    expect(loc).toMatch(/\/admin\/login/);
  });

  test("/auth/login sets the abs_session cookie via Caddy", async ({
    request,
  }) => {
    const cookie = await loginThroughCaddy(request);
    expect(cookie.name).toBe(COOKIE_NAME);
    expect(cookie.value.length).toBeGreaterThan(8);
  });

  test("admin lands on /admin/dashboard after login", async ({
    browser,
  }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      // Drive the login through the same backend endpoint Next.js uses.
      const apiResponse = await ctx.request.post(
        `${PROD_BASE_URL}/auth/login`,
        { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } },
      );
      expect(apiResponse.ok()).toBeTruthy();

      const page = await ctx.newPage();
      const navigation = await page.goto(
        `${PROD_BASE_URL}/admin/dashboard`,
        { waitUntil: "domcontentloaded" },
      );
      // Either rendered (200) or middleware accepted the cookie and
      // proxied the dashboard payload — never a redirect to /admin/login.
      expect(navigation?.status() ?? 0).toBeLessThan(400);
      expect(page.url()).toMatch(/\/admin\/dashboard$/);
    } finally {
      await ctx.close();
    }
  });
});
