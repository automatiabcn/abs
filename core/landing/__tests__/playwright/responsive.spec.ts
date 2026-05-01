// T-Q04 — responsive smoke: home + pricing render correctly at 3 breakpoints.
import { test, expect } from "@playwright/test";

const BREAKPOINTS = [
  { name: "mobile-360", width: 360, height: 800 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 900 },
] as const;

const ROUTES = ["/", "/pricing"] as const;

for (const route of ROUTES) {
  for (const bp of BREAKPOINTS) {
    test(`responsive ${route} @ ${bp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      const resp = await page.goto(route, { waitUntil: "domcontentloaded" });
      expect(resp!.status()).toBe(200);

      // Body must render.
      const bodyText = await page.locator("body").innerText();
      expect(bodyText.trim().length).toBeGreaterThan(20);

      // No horizontal scroll on mobile (common bug).
      if (bp.width <= 480) {
        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
        expect(
          scrollWidth - clientWidth,
          `${route} ${bp.name} horizontal scroll`,
        ).toBeLessThanOrEqual(2);
      }
    });
  }
}
