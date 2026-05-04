// Q12-L18 — Cold-cache first-visit LCP probe.
//
// Sprint 21 honest report measured LCP under warm-cache Playwright runs.
// A fresh KOBİ pilot demo opens cold: no service worker, empty HTTP
// cache, no localStorage. This spec enforces a per-page LCP budget under
// genuine cold-cache conditions.
//
// Each test creates an isolated browser context with `serviceWorkers:
// "block"` and a one-time bypass of HTTP caching via the `Cache-Control`
// request override. For authenticated panel routes the seeded
// `abs_session` JWT is loaded from /tmp/q12_cookie.txt (curl-driven login
// step in master_repro.sh).
import { test, expect, BrowserContext } from "@playwright/test";
import * as fs from "node:fs";

interface PageBudget {
  path: string;
  authed: boolean;
  budgetMs: number;
}

const PUBLIC_BUDGETS: PageBudget[] = [
  { path: "/",                   authed: false, budgetMs: 3500 },
  { path: "/pricing",            authed: false, budgetMs: 3500 },
  { path: "/showcase",           authed: false, budgetMs: 3500 },
  { path: "/onboarding",         authed: false, budgetMs: 3500 },
];

const PANEL_BUDGETS: PageBudget[] = [
  { path: "/panel",              authed: true,  budgetMs: 4500 },
  { path: "/panel/chat",         authed: true,  budgetMs: 5500 }, // Sprint 21 acknowledged regression
  { path: "/panel/tools",        authed: true,  budgetMs: 5500 },
  { path: "/panel/quota",        authed: true,  budgetMs: 4500 },
  { path: "/panel/meetings",     authed: true,  budgetMs: 4500 },
  { path: "/panel/transcription",authed: true,  budgetMs: 4500 },
  { path: "/admin/marketplace",  authed: true,  budgetMs: 4500 },
  { path: "/admin/providers",    authed: true,  budgetMs: 4500 },
  { path: "/admin/workflow-builder", authed: true, budgetMs: 5500 },
  // Q12 R66 — Sprint 22 RSC Phase B targets. Pre-R64/R65 these
  // routes were "use client" whole-page components that did a post-
  // hydration XHR to /v1/admin/audit/recent and /v1/admin/users
  // respectively. Now they're split-shells (server fetch → client
  // island via initialData), so the first-XHR round-trip is gone.
  // Budget 4500 ms matches the other admin routes; once the LCP
  // delta is captured (R66 artifact) we can tighten it further.
  { path: "/admin/audit",        authed: true,  budgetMs: 4500 },
  { path: "/admin/users",        authed: true,  budgetMs: 4500 },
];

const ALL_BUDGETS: PageBudget[] = [...PUBLIC_BUDGETS, ...PANEL_BUDGETS];

interface ColdSample {
  lcp: number;
  fcp: number;
  ttfb: number;
}

async function collectColdLcp(page: import("@playwright/test").Page): Promise<ColdSample> {
  return page.evaluate<ColdSample>(
    () =>
      new Promise<ColdSample>((resolve) => {
        const sample: ColdSample = { lcp: 0, fcp: 0, ttfb: 0 };
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
              if (e.entryType === "largest-contentful-paint") {
                sample.lcp = Math.max(sample.lcp, e.startTime);
              }
              if (e.entryType === "paint" && e.name === "first-contentful-paint") {
                sample.fcp = e.startTime;
              }
            }
          }).observe({ type: "largest-contentful-paint", buffered: true });
        } catch (_e) { /* no-op */ }
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
              if (e.entryType === "paint" && e.name === "first-contentful-paint") {
                sample.fcp = e.startTime;
              }
            }
          }).observe({ type: "paint", buffered: true });
        } catch (_e) { /* no-op */ }
        try {
          const navEntry = performance.getEntriesByType("navigation")[0] as
            | PerformanceNavigationTiming
            | undefined;
          if (navEntry) sample.ttfb = navEntry.responseStart;
        } catch (_e) { /* no-op */ }
        setTimeout(() => resolve(sample), 3000);
      }),
  );
}

function loadAuthCookie(): { name: string; value: string; domain: string; path: string } | null {
  try {
    const raw = fs.readFileSync("/tmp/q12_cookie.txt", "utf-8");
    for (const rawLine of raw.split("\n")) {
      // Netscape cookie file uses `#HttpOnly_<domain>` for HttpOnly entries.
      // Strip that prefix; skip pure comment lines (`# ...`).
      if (!rawLine) continue;
      let line = rawLine;
      if (line.startsWith("#HttpOnly_")) line = line.slice("#HttpOnly_".length);
      else if (line.startsWith("#")) continue;
      const parts = line.split(/\t+/);
      // domain TAB flag TAB path TAB secure TAB expiry TAB name TAB value
      if (parts.length >= 7 && parts[5] === "abs_session") {
        return { name: parts[5], value: parts[6], domain: "localhost", path: "/" };
      }
    }
  } catch (_e) {
    /* no cookie — auth tests will skip */
  }
  return null;
}

async function primeColdContext(ctx: BrowserContext, withAuth: boolean): Promise<boolean> {
  // No service workers, fresh storage state — already enforced by per-test
  // context. Explicitly clear anything that might survive.
  await ctx.clearCookies();
  if (withAuth) {
    const cookie = loadAuthCookie();
    if (!cookie) return false;
    await ctx.addCookies([
      { ...cookie, expires: Math.floor(Date.now() / 1000) + 3600 },
    ]);
  }
  return true;
}

test.describe.configure({ mode: "serial" });

for (const target of ALL_BUDGETS) {
  test(`q12-l18 cold-cache LCP ${target.path}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      serviceWorkers: "block",
      // Disable HTTP cache by bypassing on every request.
      extraHTTPHeaders: { "Cache-Control": "no-cache, no-store, must-revalidate" },
    });
    const ready = await primeColdContext(ctx, target.authed);
    if (target.authed && !ready) {
      test.skip(true, "abs_session cookie missing — run master_repro.sh prep");
      await ctx.close();
      return;
    }

    const page = await ctx.newPage();
    await page.goto(target.path, { waitUntil: "networkidle", timeout: 30_000 });
    const sample = await collectColdLcp(page);

    // eslint-disable-next-line no-console
    console.log(
      `Q12-L18 cold ${target.path} LCP=${Math.round(sample.lcp)}ms ` +
      `FCP=${Math.round(sample.fcp)}ms TTFB=${Math.round(sample.ttfb)}ms ` +
      `budget=${target.budgetMs}ms`,
    );

    expect(
      sample.lcp,
      `${target.path} cold-cache LCP exceeded budget (${sample.lcp}ms > ${target.budgetMs}ms)`,
    ).toBeLessThanOrEqual(target.budgetMs);

    await ctx.close();
  });
}
