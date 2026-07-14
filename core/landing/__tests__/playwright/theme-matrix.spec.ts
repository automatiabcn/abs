// Q10 Round 7 / L3 — themed walkthrough across 15 panel surfaces.
// For each page we toggle next-themes between dark and light via the
// localStorage 'theme' key, reload, and assert: no console errors, the
// `data-page` selector renders, and `documentElement` carries the
// expected class name (`dark` or absence of it).

import { test, expect, type ConsoleMessage, type Page } from "@playwright/test";

const HARMLESS = ["Stripe", "favicon", "DevTools", "next-router-mock"];

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
  { slug: "graph",         path: "/admin/graph",           marker: '[data-page="admin-graph"]' },
  { slug: "settings",      path: "/admin/settings",        marker: '[data-page="admin-settings"]' },
  { slug: "audit",         path: "/admin/audit",           marker: '[data-page="admin-audit"]' },
  { slug: "users",         path: "/admin/users",           marker: '[data-page="admin-users"]' },
  { slug: "meetings",      path: "/panel/meetings",        marker: '[data-page="panel-meetings"]' },
  { slug: "transcription", path: "/panel/transcription",   marker: '[data-page="panel-transcription"]' },
  { slug: "workflow",      path: "/admin/workflow-builder",marker: '[data-testid="workflow-canvas-title"]' },
];

const THEMES = ["dark", "light"] as const;

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
    .post("/auth/login", {
      data: { email, password },
    })
    .catch(() => null);
}

test.describe("Q10/L3 — theme matrix walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await loginIfNeeded(page);
  });

  for (const theme of THEMES) {
    for (const s of SURFACES) {
      test(`${s.slug} · ${theme}`, async ({ page }) => {
        const errors: string[] = [];
        consoleSink(page, errors);

        // Seed next-themes via localStorage before navigation; the
        // PanelThemeProvider reads it on mount.
        await page.addInitScript((t: string) => {
          window.localStorage.setItem("theme", t);
        }, theme);

        const resp = await page.goto(s.path, { waitUntil: "domcontentloaded" });
        expect(resp).not.toBeNull();
        expect([200, 302, 304]).toContain(resp!.status());

        const onLogin = page.url().includes("/login");
        if (!onLogin) {
          await expect(page.locator(s.marker).first()).toBeVisible({
            timeout: 8000,
          });
          // documentElement.classList carries 'dark' for next-themes
          // when class strategy is in use.
          const cls = await page.evaluate(() =>
            document.documentElement.classList.toString(),
          );
          if (theme === "dark") {
            expect(cls).toContain("dark");
          } else {
            expect(cls).not.toContain("dark");
          }
        }

        const harmful = errors.filter(
          (line) => !HARMLESS.some((needle) => line.includes(needle)),
        );
        expect(
          harmful,
          `${s.slug}/${theme} console errors: ${harmful.join(" | ")}`,
        ).toEqual([]);
      });
    }
  }
});
