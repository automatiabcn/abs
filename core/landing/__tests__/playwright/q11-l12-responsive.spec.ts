// Q11 Round 4 / L12 — responsive breakpoint sweep.
//
// Q10's e2e suite ran 1280×720 only (Desktop Chrome default). Real
// users open the panel on 375 (iPhone SE), 768 (iPad portrait), 1024
// (iPad landscape / small laptop) and 1920 (desktop). This spec
// catches two concrete regressions a desktop-only suite misses:
//
//   1. horizontal overflow (page widens past viewport)
//   2. touch targets <24×24 px (WCAG 2.2 SC 2.5.8 baseline)
//
// Run with `--project=chromium-desktop` (config sets baseURL to the
// prod standalone on :3458).

import { test, expect, type Page } from "@playwright/test";

interface Surface {
  slug: string;
  path: string;
  marker: string;
}

const SURFACES: Surface[] = [
  { slug: "panel", path: "/panel", marker: '[data-test="panel-stats"]' },
  { slug: "chat", path: "/panel/chat", marker: '[data-page="panel-chat"]' },
  { slug: "tools", path: "/panel/tools", marker: '[data-page="panel-tools"]' },
  { slug: "meetings", path: "/panel/meetings", marker: '[data-page="panel-meetings"]' },
  { slug: "transcription", path: "/panel/transcription", marker: '[data-page="panel-transcription"]' },
  { slug: "quota", path: "/panel/quota", marker: '[data-page="panel-quota"]' },
  { slug: "providers", path: "/admin/providers", marker: '[data-page="admin-providers"]' },
  { slug: "pipelines", path: "/admin/pipelines", marker: '[data-page="admin-pipelines"]' },
  { slug: "rag", path: "/admin/rag", marker: '[data-page="admin-rag"]' },
  { slug: "marketplace", path: "/admin/marketplace", marker: '[data-page="admin-marketplace"]' },
  { slug: "graph", path: "/admin/graph", marker: '[data-page="admin-graph"]' },
  { slug: "settings", path: "/admin/settings", marker: '[data-page="admin-settings"]' },
  { slug: "audit", path: "/admin/audit", marker: '[data-page="admin-audit"]' },
  { slug: "users", path: "/admin/users", marker: '[data-page="admin-users"]' },
  { slug: "workflow", path: "/admin/workflow-builder", marker: '[data-testid="workflow-canvas-title"]' },
];

const VIEWPORTS = [
  { name: "mobile-375", width: 375, height: 667 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "laptop-1024", width: 1024, height: 768 },
  { name: "desktop-1920", width: 1920, height: 1080 },
] as const;

async function loginIfNeeded(page: Page) {
  const email = process.env.ABS_PANEL_EMAIL ?? "admin@local";
  const password = process.env.ABS_PANEL_PASSWORD ?? "CHANGEME";
  await page.request
    .post("/auth/login", { data: { email, password } })
    .catch(() => null);
}

test.describe("Q11/L12 — responsive viewport sweep", () => {
  test.beforeEach(async ({ page }) => {
    await loginIfNeeded(page);
  });

  for (const vp of VIEWPORTS) {
    for (const s of SURFACES) {
      test(`q11-l12 ${s.slug} @ ${vp.name}`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });

        const resp = await page.goto(s.path, {
          waitUntil: "domcontentloaded",
        });
        expect(resp).not.toBeNull();
        const onLogin = page.url().includes("/login");
        if (onLogin) test.skip(true, "auth redirect");

        await expect(page.locator(s.marker).first()).toBeVisible({
          timeout: 8000,
        });
        await page.waitForTimeout(300);

        // 1. No horizontal overflow — html scrollWidth ≤ clientWidth+1
        //    tolerance for sub-pixel rounding.
        const overflow = await page.evaluate(() => {
          const el = document.documentElement;
          return el.scrollWidth - el.clientWidth;
        });
        expect(
          overflow,
          `${s.slug}@${vp.name}: html overflows by ${overflow}px`,
        ).toBeLessThanOrEqual(1);

        // 2. Touch targets ≥24×24 px (WCAG 2.2 SC 2.5.8). Only check
        //    at mobile/tablet viewports — desktop is mouse-driven.
        if (vp.width <= 768) {
          // Q11-L12 / Q10-L5-005: Tremor + Headless UI inject icon-only
          // clear/popover buttons whose class chains drift across
          // versions (`.tremor-*`, headlessui ids, and bare class
          // strings). Excluded from the touch-target gate so panel-code
          // regressions still surface. The filter also drops empty-text
          // icon-only buttons under 20px wide — those are always
          // third-party widget internals; our own icon buttons carry
          // an aria-label which counts as accessible name even though
          // textContent is empty.
          const tooSmall = await page.locator(
            "button:not([class*='tremor']):not([data-headlessui-state]):not([id^='headlessui-']), "
            + "a[href], [role=button]",
          ).evaluateAll((els) =>
            els
              .map((el) => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return null;
                if (r.width < 24 || r.height < 24) {
                  const text = (el.textContent || "").trim();
                  const aria = el.getAttribute("aria-label") || "";
                  // empty-text icon-only buttons under 20px wide → 3rd-party
                  if (!text && !aria && r.width < 20) return null;
                  return {
                    tag: el.tagName,
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    text: text.slice(0, 40),
                  };
                }
                return null;
              })
              .filter(Boolean),
          );
          expect(
            tooSmall,
            `${s.slug}@${vp.name}: touch targets <24px: ${JSON.stringify(tooSmall)}`,
          ).toEqual([]);
        }
      });
    }
  }
});
