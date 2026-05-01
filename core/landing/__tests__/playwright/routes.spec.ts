// T-Q02 — every public route must return 200 and render without console errors.
import { test, expect, type ConsoleMessage } from "@playwright/test";

const ROUTES = [
  { path: "/", name: "home" },
  { path: "/pricing", name: "pricing" },
  { path: "/beta", name: "beta" },
  { path: "/connect", name: "connect" },
  { path: "/privacy", name: "privacy" },
  { path: "/terms", name: "terms" },
  { path: "/refund", name: "refund" },
  { path: "/success", name: "success" },
];

for (const route of ROUTES) {
  test(`route ${route.name} (${route.path}) returns 200 + no console error`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg: ConsoleMessage) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err: Error) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    const resp = await page.goto(route.path, { waitUntil: "domcontentloaded" });
    expect(resp, `no response for ${route.path}`).not.toBeNull();
    expect(resp!.status(), `${route.path} status`).toBe(200);

    // Page must actually render *something* — no completely blank body.
    const bodyText = await page.locator("body").innerText();
    expect(bodyText.trim().length, `${route.path} empty body`).toBeGreaterThan(20);

    // Tolerate a few well-known dev-mode warnings; fail on anything else.
    const harmful = consoleErrors.filter(
      (line) =>
        !line.includes("Stripe") && // Stripe.js isn't loaded in test env
        !line.includes("favicon") &&
        !line.includes("DevTools"),
    );
    expect(harmful, `${route.path} console errors: ${harmful.join(" | ")}`).toEqual([]);
  });
}

test("/nope404 returns 404", async ({ page }) => {
  const resp = await page.goto("/nope404", { waitUntil: "domcontentloaded" });
  expect(resp!.status()).toBe(404);
});
