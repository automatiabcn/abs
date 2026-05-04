// Q12-L18 (S6 R36) — Service Worker registration + cache strategies.
//
// Asserts:
//   1. /sw.js is reachable + has the abs-panel-cache-v1 marker
//   2. ServiceWorkerRegister mounts under /panel/* and registers
//   3. /v1/* and /_next/* pass through (NEVER cached)
//   4. cache-first / network-first / stale-while-revalidate strategy
//      bookkeeping (cache name + GET-only + non-/v1 routing)
//
// Strategy correctness assertions are *static* — they read the SW
// source and verify the dispatch rules. End-to-end cache-hit
// assertions belong in the L26 long-running suite.

import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

test.describe("Q12-L18 SW cache — 3 strategies", () => {
  test("sw.js shipped + version marker", async ({ page }) => {
    const r = await page.goto("/sw.js");
    expect(r?.status()).toBe(200);
    const body = (await r?.text()) ?? "";
    expect(body).toContain("abs-panel-cache-v1");
    expect(body).toContain("/panel/chat");
    expect(body).toContain("/panel/rag");
    expect(body).toContain("/panel/dashboard");
    expect(body).toContain("skipWaiting");
    expect(body).toContain("clients.claim");
  });

  test("sw.js exclusion list — /v1/, /_next/, /auth/ pass through", async ({
    page,
  }) => {
    const r = await page.goto("/sw.js");
    const body = (await r?.text()) ?? "";
    expect(body).toMatch(/path\.startsWith\(["']\/v1\/["']\)/);
    expect(body).toMatch(/path\.startsWith\(["']\/_next\/["']\)/);
    expect(body).toMatch(/path\.startsWith\(["']\/auth\/["']\)/);
    // Non-GET methods bypass.
    expect(body).toMatch(/method\s*!==?\s*["']GET["']/);
  });

  test("3 strategy functions present + correctly dispatched", async () => {
    // Static source check — the SW should expose three named
    // strategies and dispatch each route group to the right one.
    const swPath = path.join(
      process.cwd(),
      "public",
      "sw.js",
    );
    const src = fs.readFileSync(swPath, "utf-8");
    expect(src).toMatch(/async function cacheFirst\(/);
    expect(src).toMatch(/async function networkFirst\(/);
    expect(src).toMatch(/async function staleWhileRevalidate\(/);
    // Dispatch order: chat → cache-first, rag → SWR, dashboard|/panel → network-first.
    expect(src).toMatch(
      /\/panel\/chat[\s\S]*?cacheFirst/,
    );
    expect(src).toMatch(
      /\/panel\/rag[\s\S]*?staleWhileRevalidate/,
    );
    expect(src).toMatch(
      /\/panel\/dashboard[\s\S]*?networkFirst/,
    );
  });

  test("network-first uses 3s timeout for fallback", async () => {
    const swPath = path.join(
      process.cwd(),
      "public",
      "sw.js",
    );
    const src = fs.readFileSync(swPath, "utf-8");
    // Timeout should be 3000ms (the panel chrome p95 is ~120ms;
    // 3s is comfortably above the slowest non-error case).
    expect(src).toMatch(/NETWORK_TIMEOUT_MS\s*=\s*3000/);
  });

  test("ServiceWorkerRegister component mounts under /panel layout", async () => {
    const layoutPath = path.join(
      process.cwd(),
      "app",
      "panel",
      "layout.tsx",
    );
    const src = fs.readFileSync(layoutPath, "utf-8");
    expect(src).toContain("ServiceWorkerRegister");
    expect(src).toContain("<ServiceWorkerRegister />");
  });
});
