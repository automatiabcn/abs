// Verify the billing kill-switch disables every CTA on the
// pricing surfaces. Default (no NEXT_PUBLIC_BILLING_ENABLED set) → all
// disabled.
import { test, expect } from "@playwright/test";

test("/showcase pricing buttons are disabled by default", async ({ page }) => {
  await page.goto("/showcase", { waitUntil: "domcontentloaded" });

  const buttons = await page.locator('[data-component="pricing-tier"] button').all();
  expect(buttons.length).toBeGreaterThanOrEqual(3);

  for (const btn of buttons) {
    await expect(btn).toBeDisabled();
    await expect(btn).toHaveAttribute("aria-disabled", "true");
  }
});

test("/showcase gated wrapper carries data-billing-gated", async ({ page }) => {
  await page.goto("/showcase", { waitUntil: "domcontentloaded" });
  const wrappers = page.locator('[data-billing-gated="true"]');
  await expect(wrappers).toHaveCount(3);
});

test("/pricing CheckoutButton routes are disabled", async ({ page }) => {
  await page.goto("/pricing", { waitUntil: "domcontentloaded" });
  const buttons = page.locator('[data-testid^="pricing-plan-"] button');
  const count = await buttons.count();
  expect(count).toBeGreaterThanOrEqual(3);
  for (let i = 0; i < count; i++) {
    await expect(buttons.nth(i)).toBeDisabled();
  }
});

test("/showcase Header has no Manage modal trigger when gated", async ({ page }) => {
  await page.goto("/showcase", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "Manage" })).toHaveCount(0);
});
