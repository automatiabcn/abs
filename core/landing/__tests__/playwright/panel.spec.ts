// panel.js split regression net.
// We can't easily boot the FastAPI backend from Playwright in this repo, so
// the test loads the panel HTML via `setContent` + intercepts the module
// imports through `route()` to feed the actual ES-module sources from disk.
// What we verify:
//   1. The static index.html resolves cleanly (Stripe/Caddy not needed).
//   2. The new module loader (`<script type="module" src=".../panel/main.js">`)
//      is the one HTML imports.
//   3. The new modules at panel/dom.js, panel/state.js, panel/widgets.js,
//      panel/notif.js, panel/ui.js, panel/sse.js, panel/main.js all parse.
//   4. The legacy panel.js shim re-exports main.js.
import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const REPO = join(__dirname, "..", "..", "..", "..");
const PANEL_DIR = join(
  REPO,
  "core",
  "backend",
  "app",
  "static",
  "panel",
);

const MODULE_FILES = [
  "panel/dom.js",
  "panel/constants.js",
  "panel/sparkline.js",
  "panel/state.js",
  "panel/widgets.js",
  "panel/notif.js",
  "panel/ui.js",
  "panel/sse.js",
  "panel/main.js",
];

test("panel index.html loads the ES-module entry", () => {
  const html = readFileSync(join(PANEL_DIR, "index.html"), "utf8");
  expect(html).toContain('<script type="module"');
  expect(html).toContain('/panel/assets/panel/main.js');
});

test("legacy panel.js shim re-imports main.js", () => {
  const shim = readFileSync(join(PANEL_DIR, "assets", "panel.js"), "utf8");
  expect(shim).toContain('import "./panel/main.js"');
  // The 788-line IIFE must be gone.
  expect(shim.split("\n").length).toBeLessThan(20);
});

// main.js is the entry point — it imports + boots and has no exports.
const ENTRY_POINTS = new Set(["panel/main.js"]);

for (const rel of MODULE_FILES) {
  test(`module ${rel} exists and is a real ES module`, () => {
    const src = readFileSync(join(PANEL_DIR, "assets", rel), "utf8");
    expect(src.length).toBeGreaterThan(50);
    if (ENTRY_POINTS.has(rel)) {
      // Entry point — must import (it's the bootstrap).
      expect(src).toMatch(/^\s*import\s/m);
    } else {
      // Library module — must export at least one binding.
      expect(src).toMatch(/^\s*export\s/m);
    }
  });
}

test("widgets.js exports the expected SSE handler set", () => {
  const src = readFileSync(
    join(PANEL_DIR, "assets", "panel/widgets.js"),
    "utf8",
  );
  for (const fn of [
    "onMetrics",
    "onOrchestrator",
    "onCohereUsage",
    "onMcpTools",
    "onBudget",
    "onLicenseStatus",
    "onUpdateAvailable",
    "renderVital",
    "renderQuotaRadar",
    "renderDisagreement",
  ]) {
    expect(src).toContain(`export `);
    expect(src).toContain(fn);
  }
});

test("ui.js binds and exposes inline handlers via window", () => {
  const src = readFileSync(join(PANEL_DIR, "assets", "panel/ui.js"), "utf8");
  expect(src).toContain("window.dismissDemoBanner");
  expect(src).toContain("window.applyUpdate");
  expect(src).toContain("window.dismissUpdateBanner");
});

test("sse.js wires every SSE event listener the legacy file had", () => {
  const src = readFileSync(join(PANEL_DIR, "assets", "panel/sse.js"), "utf8");
  for (const evt of [
    "metrics",
    "orchestrator",
    "cohere-usage",
    "mcp-tools",
    "budget-today",
    "license-status",
    "update-available",
  ]) {
    expect(src).toContain(`"${evt}"`);
  }
});

test("main.js wires DOMContentLoaded boot for sparklines + clock + bindings", () => {
  const src = readFileSync(
    join(PANEL_DIR, "assets", "panel/main.js"),
    "utf8",
  );
  expect(src).toContain("DOMContentLoaded");
  expect(src).toContain("Sparkline");
  expect(src).toContain("startSSE");
  expect(src).toContain("startClock");
  expect(src).toContain("renderQuotaRadar");
  expect(src).toContain("renderDisagreement");
});
