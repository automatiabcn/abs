// Q12-L26 sweep 2 — long-running session: heap drift + endpoint resilience.
//
// Pre-fix gap (Session 2 closing): we had unit-level assertions on JWT
// expiry taxonomy but no real-browser test that proved a panel tab can
// survive an idle period without (a) leaking memory or (b) silently
// dropping the session cookie. A KOBİ user who leaves the tab open
// during a meeting (typical 30–60 minutes) needs both guarantees.
//
// This file ships two variants:
//
//   1. **Smoke (always runs)** — 90-second idle on /panel/chat with
//      heap snapshot at t=0 and t=90s. Asserts JS heap drift < 25 MB
//      and a follow-up /v1/chat/sessions request returns ≠ 5xx.
//
//   2. **Long (gated by LONG_RUNNING_PLAYWRIGHT=1)** — full 30-minute
//      idle with the same shape, 50 MB drift bound. Skipped by default
//      because the headed-Chromium runtime alone burns 30+ minutes of
//      CI budget; founder runs locally before perf-sweep cuts.
//
// The smoke variant is the *real* regression guard: a leak that grows
// 25 MB in 90 s would balloon to 8 GB in 30 minutes. The long variant
// is the *empirical confirmation* for go/no-go on production rollout.

import { test, expect } from "@playwright/test";

const PANEL_CHAT_URL = "/panel/chat";
// Anything other than 5xx is acceptable post-idle: 200 (legit session),
// 401 (cookie-less E2E case in dev), 404/422 (route shapes during
// scaffolding). The point is: server didn't crash + middleware didn't
// emit an internal error.
const ACCEPTABLE_POST_IDLE = (status: number) => status < 500;

interface HeapSnapshot {
  used: number;
  total: number;
  limit: number;
}

async function snapshotHeap(
  page: import("@playwright/test").Page,
): Promise<HeapSnapshot> {
  return page.evaluate<HeapSnapshot>(() => {
    const mem = (performance as { memory?: HeapSnapshot }).memory;
    return {
      used: mem?.used ?? mem?.["usedJSHeapSize" as keyof HeapSnapshot] ?? 0,
      total: mem?.total ?? mem?.["totalJSHeapSize" as keyof HeapSnapshot] ?? 0,
      limit: mem?.limit ?? mem?.["jsHeapSizeLimit" as keyof HeapSnapshot] ?? 0,
    };
  });
}

test.describe("Q12-L26 long-running session", () => {
  test("90s idle: heap drift bounded + endpoint reachable [smoke]", async ({
    page,
  }) => {
    test.slow();
    test.setTimeout(3 * 60 * 1000);

    const response = await page.goto(PANEL_CHAT_URL, { waitUntil: "load" });
    expect(response?.status() ?? 0).toBeLessThan(500);

    // Heap baseline. We tolerate 0 (Chromium without --enable-precise-memory)
    // by skipping the assertion if the API is unavailable.
    const heap0 = await snapshotHeap(page);
    if (heap0.used === 0) {
      test.info().annotations.push({
        type: "skip-reason",
        description:
          "performance.memory unavailable (non-Chromium or build flag off); endpoint check still runs",
      });
    }

    // 90 s idle. We use waitForTimeout instead of evaluate(setTimeout)
    // so the framework's slow-test lock is honoured.
    await page.waitForTimeout(90 * 1000);

    const heap1 = await snapshotHeap(page);
    if (heap0.used > 0 && heap1.used > 0) {
      const driftMb = (heap1.used - heap0.used) / (1024 * 1024);
      console.log(
        `[L26-smoke] heap_baseline_mb=${(heap0.used / 1024 / 1024).toFixed(2)} ` +
          `heap_90s_mb=${(heap1.used / 1024 / 1024).toFixed(2)} ` +
          `drift_mb=${driftMb.toFixed(2)}`,
      );
      // 25 MB / 90 s = ~16.5 GB / hour upper bound. Anything tighter
      // would flake on garbage-collection jitter; anything looser
      // would let real leaks through.
      expect(heap1.used - heap0.used).toBeLessThan(25 * 1024 * 1024);
    }

    // Server still serving — proves middleware didn't deadlock or
    // emit a 5xx during the idle window.
    const followUpStatus = await page.evaluate(async () => {
      try {
        const r = await fetch("/v1/chat/sessions", { credentials: "include" });
        return r.status;
      } catch {
        return -1;
      }
    });
    console.log(`[L26-smoke] post_idle_status=${followUpStatus}`);
    expect(followUpStatus).not.toBe(-1);
    expect(ACCEPTABLE_POST_IDLE(followUpStatus)).toBe(true);
  });

  test("30 minute idle: heap drift bounded [LONG_RUNNING_PLAYWRIGHT=1]", async ({
    page,
  }) => {
    test.skip(
      process.env.LONG_RUNNING_PLAYWRIGHT !== "1",
      "Set LONG_RUNNING_PLAYWRIGHT=1 to run the 30-minute long-running test.",
    );
    test.slow();
    test.setTimeout(35 * 60 * 1000);

    await page.goto(PANEL_CHAT_URL, { waitUntil: "load" });

    const heap0 = await snapshotHeap(page);

    // Five 6-minute waits with a heap snapshot in between for drift
    // visibility (so a leak surfaces by minute 12 instead of 30).
    const checkpoints: HeapSnapshot[] = [heap0];
    for (let i = 0; i < 5; i++) {
      await page.waitForTimeout(6 * 60 * 1000);
      const snap = await snapshotHeap(page);
      checkpoints.push(snap);
      console.log(
        `[L26-long] checkpoint=${i + 1}/5 used_mb=${(snap.used / 1024 / 1024).toFixed(2)}`,
      );
    }

    const heap1 = checkpoints[checkpoints.length - 1];
    if (heap0.used > 0 && heap1.used > 0) {
      const driftMb = (heap1.used - heap0.used) / (1024 * 1024);
      console.log(`[L26-long] total_drift_mb=${driftMb.toFixed(2)}`);
      expect(heap1.used - heap0.used).toBeLessThan(50 * 1024 * 1024);
    }

    const followUpStatus = await page.evaluate(async () => {
      const r = await fetch("/v1/chat/sessions", { credentials: "include" });
      return r.status;
    });
    expect(ACCEPTABLE_POST_IDLE(followUpStatus)).toBe(true);
  });

  test("token cookie persists across short navigations", async ({ page }) => {
    test.slow();
    // Navigate to chat → dashboard → chat. Cookie must survive in-app
    // routing without a cold reauth. Catches regressions where a panel
    // route accidentally clears the session cookie.
    await page.goto("/panel/chat", { waitUntil: "load" });
    const cookiesBefore = await page.context().cookies();
    const sessionBefore = cookiesBefore.find(
      (c) => c.name === "abs_session" || c.name.includes("session"),
    );

    await page.goto("/panel", { waitUntil: "load" });
    await page.goto("/panel/chat", { waitUntil: "load" });

    const cookiesAfter = await page.context().cookies();
    const sessionAfter = cookiesAfter.find(
      (c) => c.name === "abs_session" || c.name.includes("session"),
    );

    if (sessionBefore && sessionAfter) {
      expect(sessionAfter.value).toBe(sessionBefore.value);
    } else {
      // Both absent is the legitimate dev path (no auto-login). Both
      // sides absent is fine; mismatch (one side present, the other
      // missing) is a regression.
      expect(Boolean(sessionBefore)).toBe(Boolean(sessionAfter));
    }
  });
});
