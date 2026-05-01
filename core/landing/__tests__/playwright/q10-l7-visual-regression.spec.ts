// Q10 Round 9 / L7 — visual regression baseline + diff.
//
// First run: snapshots get written under `__tests__/playwright/q10-l7-visual-regression.spec.ts-snapshots/`.
// Second run: every page is diffed against the baseline; any pixel
// delta beyond the configured threshold fails the test, surfacing the
// PR-level UI regression.
//
// Pages capture default-theme dark-mode (panel default). Light variant
// is left for a later round to keep baseline cardinality manageable.

import { test, expect, type Page } from "@playwright/test";

interface Surface {
  slug: string;
  path: string;
  marker: string;
}

const SURFACES: Surface[] = [
  { slug: "panel",         path: "/panel",                 marker: '[data-test="panel-stats"]' },
  { slug: "chat",          path: "/panel/chat",            marker: '[data-page="panel-chat"]' },
  { slug: "tools",         path: "/panel/tools",           marker: '[data-page="panel-tools"]' },
  { slug: "providers",     path: "/admin/providers",       marker: '[data-page="admin-providers"]' },
  { slug: "pipelines",     path: "/admin/pipelines",       marker: '[data-page="admin-pipelines"]' },
  { slug: "rag",           path: "/admin/rag",             marker: '[data-page="admin-rag"]' },
  { slug: "marketplace",   path: "/admin/marketplace",     marker: '[data-page="admin-marketplace"]' },
  { slug: "quota",         path: "/panel/quota",           marker: '[data-page="panel-quota"]' },
  { slug: "settings",      path: "/admin/settings",        marker: '[data-page="admin-settings"]' },
  { slug: "users",         path: "/admin/users",           marker: '[data-page="admin-users"]' },
];

async function loginIfNeeded(page: Page) {
  const email = process.env.ABS_PANEL_EMAIL ?? "admin@local";
  const password = process.env.ABS_PANEL_PASSWORD ?? "CHANGEME";
  await page.request
    .post("/auth/login", {
      data: { email, password },
    })
    .catch(() => null);
}

test.describe("Q10/L7 — visual regression baseline", () => {
  test.beforeEach(async ({ page }) => {
    await loginIfNeeded(page);
  });

  for (const s of SURFACES) {
    test(`q10-l7 ${s.slug} screenshot`, async ({ page }) => {
      await page.goto(s.path, { waitUntil: "networkidle" });
      const onLogin = page.url().includes("/login");
      test.skip(onLogin, "auth redirect — cannot baseline login form");
      await expect(page.locator(s.marker).first()).toBeVisible({
        timeout: 8000,
      });
      // Wait for fonts + framer-motion entrance to settle so the
      // baseline isn't subject to first-paint flicker.
      await page.waitForTimeout(400);

      await expect(page).toHaveScreenshot(`${s.slug}.png`, {
        maxDiffPixelRatio: 0.02, // 2% tolerance for anti-alias drift
        animations: "disabled",
        fullPage: true,
      });
    });
  }
});
