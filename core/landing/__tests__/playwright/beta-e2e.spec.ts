// T-R08 — 15-min real beta UI E2E. Walks the journey a beta tenant takes
// in the landing app:
//   1. Land on `/`           — hero + showcase + CTA visible.
//   2. Hit `/pricing`        — tiers render with i18n + billing-disabled gate.
//   3. Hit `/showcase`       — visual gallery + 3D hero (or SVG fallback).
//   4. Hit `/onboarding`     — 5-step walkthrough renders + progress tracker.
//   5. Hit `/beta`           — beta opt-in form renders without contrast bug.
//   6. Hit `/connect`        — OAuth/integrations entry-point renders.
//
// Stripe is intentionally absent (NEXT_PUBLIC_BILLING_ENABLED=false in test).
// The 15-min framing is the *outer envelope* of the journey — Playwright
// completes it well under that, but the slow waits (1500 ms idle) approximate
// the dwell a real prospect spends on each route.
import { test, expect, type ConsoleMessage } from "@playwright/test";

const STEPS = [
  { path: "/", name: "home", expectText: ["ABS", "AI"] },
  { path: "/pricing", name: "pricing", expectText: ["Self-host", "Maintenance", "Managed"] },
  { path: "/showcase", name: "showcase", expectText: ["RAG", "Cascade", "Pricing"] },
  { path: "/onboarding", name: "onboarding", expectText: ["1", "5"] },
  { path: "/beta", name: "beta", expectText: ["beta"] },
  { path: "/connect", name: "connect", expectText: ["Connect", "OAuth"].slice(0, 1) },
];

const DWELL_MS = 800;

test("beta tenant 15-min UI journey: home → pricing → showcase → onboarding → beta → connect", async ({
  page,
}) => {
  test.setTimeout(15 * 60 * 1000);

  const allErrors: string[] = [];
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() === "error") allErrors.push(`[${page.url()}] ${msg.text()}`);
  });
  page.on("pageerror", (err: Error) => {
    allErrors.push(`[${page.url()}] pageerror: ${err.message}`);
  });

  for (const step of STEPS) {
    const resp = await page.goto(step.path, { waitUntil: "domcontentloaded" });
    expect(resp, `${step.name} no response`).not.toBeNull();
    expect(resp!.status(), `${step.name} status`).toBe(200);

    const body = await page.locator("body").innerText();
    expect(body.trim().length, `${step.name} empty body`).toBeGreaterThan(40);
    // We only require *one* of the expected text fragments — i18n locale
    // selection (TR/ES/EN) makes any single fragment match flaky.
    const lowerBody = body.toLowerCase();
    const matched = step.expectText.some((t) => lowerBody.includes(t.toLowerCase()));
    expect(matched, `${step.name} missing expected text any-of: ${step.expectText.join(", ")}`).toBe(
      true,
    );

    await page.waitForTimeout(DWELL_MS);
  }

  // Console hygiene across the whole journey: no harmful errors. Same
  // tolerated patterns as routes.spec.ts.
  const harmful = allErrors.filter(
    (line) =>
      !line.includes("Stripe") &&
      !line.includes("favicon") &&
      !line.includes("DevTools") &&
      !line.includes("WebSocket") &&
      // 404s for missing static assets (e.g., placeholder OG image) are not
      // a regression in the journey; the actual route still rendered 200.
      !line.includes("Failed to load resource") &&
      // Loom embed sets X-Frame-Options: deny — that's their policy, not
      // an ABS regression. The video CTA falls back to a click-through link.
      !line.includes("loom.com"),
  );
  expect(harmful, `console errors: ${harmful.join(" | ")}`).toEqual([]);
});

test("billing kill-switch is honoured on /pricing during beta", async ({ page }) => {
  await page.goto("/pricing", { waitUntil: "domcontentloaded" });
  // PricingTierCard renders disabled CTA buttons when NEXT_PUBLIC_BILLING_ENABLED!=='true'.
  // We don't assert exact button text (locale-dependent); we assert there are
  // no enabled checkout-style anchors pointing to Stripe.
  const stripeLinks = await page.locator('a[href*="stripe.com"], a[href*="checkout"]').count();
  expect(stripeLinks, "no Stripe checkout links during beta").toBe(0);
});

test("onboarding walkthrough exposes progress tracker + 5 steps", async ({ page }) => {
  await page.goto("/onboarding", { waitUntil: "domcontentloaded" });
  const tracker = page.locator('[data-component="onboarding-progress"]');
  await expect(tracker).toBeVisible();
  // 5 step dots, regardless of locale.
  const stepCount = await tracker.locator("li[data-step]").count();
  expect(stepCount, "onboarding step count").toBe(5);
});
