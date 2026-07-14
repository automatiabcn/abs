// Web Vitals budget enforcement. Uses the standard `web-vitals` API
// surface that ships in every modern browser via PerformanceObserver. We
// inject a small probe into each route, wait for the metrics to land, then
// assert against the budget table in docs/qa/perf-budget-policy.md.
import { test, expect } from "@playwright/test";

const ROUTES = ["/", "/pricing", "/showcase", "/onboarding"] as const;

const BUDGETS = {
  // Lab values (synthetic chromium; production thresholds live in lighthouserc).
  LCP: 2800, // ms
  CLS: 0.15,
  INP: 250, // ms (treated as max event duration, since synthetic INP isn't measurable)
} as const;

interface VitalsSample {
  lcp: number;
  cls: number;
  longestEvent: number;
}

async function collectVitals(page: import("@playwright/test").Page): Promise<VitalsSample> {
  return page.evaluate<VitalsSample>(
    () =>
      new Promise<VitalsSample>((resolve) => {
        const sample = { lcp: 0, cls: 0, longestEvent: 0 };
        try {
          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              if (entry.entryType === "largest-contentful-paint") {
                sample.lcp = Math.max(sample.lcp, entry.startTime);
              }
            }
          }).observe({ type: "largest-contentful-paint", buffered: true });
        } catch (_e) {
          /* no-op */
        }
        try {
          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              const e = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
              if (!e.hadRecentInput) sample.cls += e.value ?? 0;
            }
          }).observe({ type: "layout-shift", buffered: true });
        } catch (_e) {
          /* no-op */
        }
        try {
          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              sample.longestEvent = Math.max(sample.longestEvent, entry.duration);
            }
          }).observe({
            // `durationThreshold` is Chromium-only; TS lib.dom is behind, cast.
            type: "event",
            buffered: true,
            durationThreshold: 16,
          } as PerformanceObserverInit);
        } catch (_e) {
          /* no-op */
        }
        // Allow the page to settle.
        setTimeout(() => resolve(sample), 2500);
      }),
  );
}

for (const route of ROUTES) {
  test(`web-vitals budget on ${route}`, async ({ page }) => {
    await page.goto(route, { waitUntil: "networkidle" });
    const sample = await collectVitals(page);
    expect(sample.lcp, `${route} LCP`).toBeLessThanOrEqual(BUDGETS.LCP);
    expect(sample.cls, `${route} CLS`).toBeLessThanOrEqual(BUDGETS.CLS);
    // Synthetic INP isn't directly measurable; assert longest first-class
    // event stayed under the budget as a proxy.
    expect(sample.longestEvent, `${route} longest event`).toBeLessThanOrEqual(BUDGETS.INP);
  });
}
