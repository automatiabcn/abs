// axe-core a11y sweep across all public routes.
// Fails on any violation with impact: critical or serious.
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const ROUTES = [
  "/",
  "/pricing",
  "/beta",
  "/connect",
  "/privacy",
  "/terms",
  "/refund",
  "/success",
];

for (const path of ROUTES) {
  test(`a11y: ${path}`, async ({ page }) => {
    await page.goto(path, { waitUntil: "domcontentloaded" });
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    if (blocking.length) {
      console.log(`a11y violations on ${path}:`);
      for (const v of blocking) {
        console.log(`  - [${v.impact}] ${v.id} — ${v.help}`);
      }
    }
    expect(blocking, `${path} a11y violations`).toEqual([]);
  });
}
