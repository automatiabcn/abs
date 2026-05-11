/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 *
 * Sprint 2D ITEM-4 — Bundle threshold regression test.
 *
 * Sprint 2C raised the `*.js` catchall to 160 KB as a pragmatic workaround.
 * Sprint 2D dynamically imports Tremor charts (UsageTrendChart) and tightens
 * the thresholds: synchronous first-load chunks (main, framework, vendor) are
 * capped at <=90 KB, async heavy chunks (three.js, recharts) keep the 160 KB
 * allowance.
 *
 * Guards against future regressions where someone bumps the threshold back
 * to a single permissive catchall.
 */
import { describe, it, expect } from "vitest";
import config from "../bundlewatch.config.json";

function thresholdKbOf(path: string): number {
  const entry = config.files.find((f: { path: string }) => f.path === path);
  if (!entry) throw new Error(`bundlewatch entry missing for ${path}`);
  const m = entry.maxSize.match(/^(\d+(?:\.\d+)?)\s*kB$/i);
  if (!m) throw new Error(`unexpected maxSize: ${entry.maxSize}`);
  return Number(m[1]);
}

describe("bundlewatch.config.json — Sprint 2D thresholds", () => {
  it("framework chunk is capped at <= 65 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/framework-*.js")).toBeLessThanOrEqual(65);
  });

  it("main chunk is capped at <= 50 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/main-*.js")).toBeLessThanOrEqual(50);
  });

  it("main-app chunk is capped at <= 10 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/main-app-*.js")).toBeLessThanOrEqual(10);
  });

  it("polyfills chunk is capped at <= 50 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/polyfills-*.js")).toBeLessThanOrEqual(50);
  });

  it("numbered vendor chunks are capped at <= 90 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/*-*.js")).toBeLessThanOrEqual(90);
  });

  it("admin/usage route chunk is capped at <= 20 KB", () => {
    // Lazy AreaChart import keeps this small; regression test guards future
    // direct Tremor imports.
    expect(thresholdKbOf(".next/static/chunks/app/admin/usage/*.js")).toBeLessThanOrEqual(20);
  });

  it("login route chunk is capped at <= 10 KB", () => {
    expect(thresholdKbOf(".next/static/chunks/app/login/*.js")).toBeLessThanOrEqual(10);
  });

  it("async heavy chunks allow up to 160 KB (three.js, recharts)", () => {
    // This is the only entry that gets the 160 KB allowance, and it only
    // matches the dotted-hash async chunk naming (`<chunkId>.<hash>.js`).
    const asyncCap = thresholdKbOf(".next/static/chunks/*.*.js");
    expect(asyncCap).toBeLessThanOrEqual(160);
    expect(asyncCap).toBeGreaterThanOrEqual(120);
  });

  it("there is no blanket *.js catchall at 160 KB", () => {
    // The 2C pragmatic config had a wildcard `.next/static/chunks/*.js` at
    // 160 KB which hid regressions in first-load chunks. Sprint 2D removed
    // it in favour of scoped patterns.
    const blanket = config.files.find(
      (f: { path: string; maxSize: string }) =>
        f.path === ".next/static/chunks/*.js" && f.maxSize === "160 kB",
    );
    expect(blanket).toBeUndefined();
  });
});
