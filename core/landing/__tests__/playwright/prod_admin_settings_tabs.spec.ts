// Brief 4 R7 — /admin/settings tab navigation against the production
// stack. The settings page bundles seven tabs (Identity, Providers,
// Vault, Billing, Email, Integrations, Danger zone). Each tab updates
// the URL hash + ARIA-selected state.

import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  PROD_BASE_URL,
  requireProdStack,
} from "./helpers/prod-stack";

const EXPECTED_TABS = [
  /identity|kimlik/i,
  /provider|sağlayıcı/i,
  /vault|kasa/i,
  /billing|fatura/i,
  /email|e-?posta/i,
  /integration|entegrasyon/i,
  /danger|tehlike/i,
];

test.describe("Brief 4 R7 — admin settings tabs (production stack)", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireProdStack(request, testInfo);
  });

  test("seven tabs render and switching updates ARIA selection", async ({
    browser,
  }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await ctx.request.post(`${PROD_BASE_URL}/auth/login`, {
        data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
      });
      const page = await ctx.newPage();
      await page.goto(`${PROD_BASE_URL}/admin/settings`, {
        waitUntil: "domcontentloaded",
      });

      // Settings tablist is visible.
      const tablist = page.getByRole("tablist").first();
      await expect(tablist).toBeVisible({ timeout: 10_000 });

      const tabs = await tablist.getByRole("tab").all();
      expect(tabs.length).toBeGreaterThanOrEqual(EXPECTED_TABS.length);

      const labels = await Promise.all(
        tabs.slice(0, EXPECTED_TABS.length).map((t) => t.innerText()),
      );
      EXPECTED_TABS.forEach((rx, idx) => {
        expect(labels[idx]).toMatch(rx);
      });

      // Click the second tab; ARIA state flips.
      await tabs[1].click();
      await expect(tabs[1]).toHaveAttribute("aria-selected", "true");
      await expect(tabs[0]).toHaveAttribute("aria-selected", "false");
    } finally {
      await ctx.close();
    }
  });
});
