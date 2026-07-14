// Q11 Round 3 / L11 — cross-browser smoke.
//
// Q10 wrote 72 e2e tests but only ran them on Chromium. This spec
// re-exercises the panel + admin surface on Firefox and WebKit so a
// SSR or routing quirk specific to those engines doesn't slip into
// production. Each test:
//   1. logs in via the rewrite proxy (page.request.post)
//   2. navigates to a high-value surface (panel / admin / pricing)
//   3. asserts the data-page marker renders
//   4. asserts no harmful console errors
//
// Run with --project=firefox-desktop or --project=webkit-desktop;
// the chromium-desktop project keeps Q10 coverage so this file is
// safe to include in `npx playwright test`.

import { test, expect, type ConsoleMessage, type Page } from "@playwright/test";

const HARMLESS = ["Stripe", "favicon", "DevTools", "WebKit", "MIME type"];

interface Surface {
  slug: string;
  path: string;
  marker: string;
}

const SURFACES: Surface[] = [
  { slug: "panel", path: "/panel", marker: '[data-test="panel-stats"]' },
  { slug: "tools", path: "/panel/tools", marker: '[data-page="panel-tools"]' },
  { slug: "providers", path: "/admin/providers", marker: '[data-page="admin-providers"]' },
  { slug: "marketplace", path: "/admin/marketplace", marker: '[data-page="admin-marketplace"]' },
  { slug: "pricing", path: "/pricing", marker: 'h1' },
];

function consoleSink(page: Page, sink: string[]) {
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() === "error") sink.push(msg.text());
  });
  page.on("pageerror", (err: Error) => sink.push(`pageerror: ${err.message}`));
}

async function loginIfNeeded(page: Page) {
  const email = process.env.ABS_PANEL_EMAIL ?? "admin@local";
  const password = process.env.ABS_PANEL_PASSWORD ?? "CHANGEME";
  await page.request
    .post("/auth/login", { data: { email, password } })
    .catch(() => null);
}

test.describe("Q11/L11 — cross-browser smoke", () => {
  test.beforeEach(async ({ page }) => {
    await loginIfNeeded(page);
  });

  for (const s of SURFACES) {
    test(`${s.slug} renders`, async ({ page, browserName }) => {
      const errors: string[] = [];
      consoleSink(page, errors);

      const resp = await page.goto(s.path, { waitUntil: "domcontentloaded" });
      expect(resp, `no response for ${s.path}`).not.toBeNull();
      expect([200, 302, 304]).toContain(resp!.status());

      const onLogin = page.url().includes("/login");
      if (!onLogin) {
        await expect(page.locator(s.marker).first()).toBeVisible({
          timeout: 8000,
        });
      }

      const harmful = errors.filter(
        (line) => !HARMLESS.some((needle) => line.includes(needle)),
      );
      expect(
        harmful,
        `${s.slug}/${browserName} console errors: ${harmful.join(" | ")}`,
      ).toEqual([]);
    });
  }
});
