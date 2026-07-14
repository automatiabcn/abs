// Q12-L18 Round 9 — Cold-cache + slow-3G + CPU 4× throttle variant.
//
// Round 3 spec measured cold-cache LCP on the loopback network (≈0ms
// RTT), producing 40–324ms numbers that don't reflect KOBİ pilot
// reality. This sweep adds CDP throttling (chrome-only) so the LCP
// budget reflects what an actual fiber/3G pilot will see.
//
// Profiles tracked:
//   - slow3G:     400ms RTT, 400 KB/s down/up  (the measured baseline)
//   - lte4g:      100ms RTT, 1.5 MB/s down       (mid-tier KOBİ network)
//
// Per-page LCP budget reflects the measured value +
// 20% headroom; Q12-L18-001 throttle fidelity gap is closed when
// these numbers track the baseline within ±200ms.
import { test, expect, Page } from "@playwright/test";
import * as fs from "node:fs";

interface ThrottleProfile {
  key: "slow3G" | "lte4g";
  label: string;
  latencyMs: number;
  downloadKbps: number;
  uploadKbps: number;
  cpuRate: number;
}

const SLOW3G: ThrottleProfile = {
  key: "slow3G",
  label: "Slow 3G + CPU 4×",
  latencyMs: 400,
  downloadKbps: 3200,
  uploadKbps: 3200,
  cpuRate: 4,
};

const LTE4G: ThrottleProfile = {
  key: "lte4g",
  label: "LTE 4G + CPU 2×",
  latencyMs: 100,
  downloadKbps: 12_288,
  uploadKbps: 6144,
  cpuRate: 2,
};

interface PageBudget {
  path: string;
  authed: boolean;
  slow3GBudgetMs: number;
  lte4gBudgetMs: number;
}

const BUDGETS: PageBudget[] = [
  { path: "/",            authed: false, slow3GBudgetMs: 6000,  lte4gBudgetMs: 3500 },
  { path: "/pricing",     authed: false, slow3GBudgetMs: 6000,  lte4gBudgetMs: 3500 },
  { path: "/panel",       authed: true,  slow3GBudgetMs: 4500,  lte4gBudgetMs: 3500 },
  { path: "/panel/chat",  authed: true,  slow3GBudgetMs: 14000, lte4gBudgetMs: 6000 }, // measured 11105
  { path: "/panel/tools", authed: true,  slow3GBudgetMs: 11000, lte4gBudgetMs: 5000 }, // measured 8660
  { path: "/panel/quota", authed: true,  slow3GBudgetMs: 4500,  lte4gBudgetMs: 3500 },
  // RSC split-shell targets. Before the split these
  // routes were "use client" whole-page components that did a
  // post-hydration XHR for the initial slice. Post-split-shell the
  // server prefetches the slice and seeds React Query initialData,
  // so the SSR HTML carries rendered rows (provable: see R66
  // artifact + commit 2b196ed/2c1bb91). Slow-3G LCP is dominated by
  // the dev-mode panel JS bundle (sidebar + header + theme + query
  // client + cmdk), not the data fetch — so the split-shell win
  // shows up in TTFB / SSR-HTML readiness rather than LCP at this
  // throttle. Budgets matched to the `/panel/tools` ceiling (same
  // panel chrome shape); production-build LCP will be lower.
  { path: "/admin/audit", authed: true,  slow3GBudgetMs: 11000, lte4gBudgetMs: 5000 },
  { path: "/admin/users", authed: true,  slow3GBudgetMs: 11000, lte4gBudgetMs: 5000 },
];

interface ColdSample { lcp: number; fcp: number; ttfb: number; }

function loadAuthCookie() {
  try {
    const raw = fs.readFileSync("/tmp/q12_cookie.txt", "utf-8");
    for (const rawLine of raw.split("\n")) {
      if (!rawLine) continue;
      let line = rawLine;
      if (line.startsWith("#HttpOnly_")) line = line.slice("#HttpOnly_".length);
      else if (line.startsWith("#")) continue;
      const parts = line.split(/\t+/);
      if (parts.length >= 7 && parts[5] === "abs_session") {
        return { name: parts[5], value: parts[6], domain: "localhost", path: "/" };
      }
    }
  } catch (_e) { /* missing */ }
  return null;
}

async function applyThrottle(page: Page, profile: ThrottleProfile): Promise<void> {
  const ctx = await page.context().newCDPSession(page);
  await ctx.send("Network.enable");
  await ctx.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: profile.latencyMs,
    downloadThroughput: (profile.downloadKbps * 1024) / 8,
    uploadThroughput: (profile.uploadKbps * 1024) / 8,
  });
  await ctx.send("Emulation.setCPUThrottlingRate", { rate: profile.cpuRate });
}

async function collectLcp(page: Page): Promise<ColdSample> {
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
          const navEntry = performance.getEntriesByType("navigation")[0] as
            | PerformanceNavigationTiming | undefined;
          if (navEntry) sample.ttfb = navEntry.responseStart;
        } catch (_e) { /* no-op */ }
        // Allow 6s settle window for LCP to land under throttle.
        setTimeout(() => resolve(sample), 6000);
      }),
  );
}

test.describe.configure({ mode: "serial" });

for (const profile of [SLOW3G, LTE4G]) {
  for (const target of BUDGETS) {
    test(`throttled ${profile.key} cold-cache LCP ${target.path}`, async ({ browser, browserName }) => {
      // CDP throttle Chromium-only; skip on firefox/webkit projects.
      if (browserName !== "chromium") {
        test.skip(true, `CDP throttle Chromium-only (project=${browserName})`);
        return;
      }
      const ctx = await browser.newContext({
        serviceWorkers: "block",
        extraHTTPHeaders: { "Cache-Control": "no-cache, no-store, must-revalidate" },
      });
      await ctx.clearCookies();
      if (target.authed) {
        const cookie = loadAuthCookie();
        if (!cookie) {
          await ctx.close();
          throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );
          return;
        }
        await ctx.addCookies([{ ...cookie, expires: Math.floor(Date.now() / 1000) + 3600 }]);
      }
      const page = await ctx.newPage();
      await applyThrottle(page, profile);

      try {
        await page.goto(target.path, { waitUntil: "load", timeout: 60_000 });
      } catch (_e) {
        // Throttled networkidle is unreliable; load + manual settle is enough.
      }
      const sample = await collectLcp(page);

      const budget = profile.key === "slow3G" ? target.slow3GBudgetMs : target.lte4gBudgetMs;
      // eslint-disable-next-line no-console
      console.log(
        `Q12-L18 throttled ${profile.label} ${target.path} ` +
        `LCP=${Math.round(sample.lcp)}ms FCP=${Math.round(sample.fcp)}ms ` +
        `TTFB=${Math.round(sample.ttfb)}ms budget=${budget}ms`,
      );
      expect(
        sample.lcp,
        `${target.path} ${profile.label} LCP exceeded budget (${sample.lcp}ms > ${budget}ms)`,
      ).toBeLessThanOrEqual(budget);

      await ctx.close();
    });
  }
}
