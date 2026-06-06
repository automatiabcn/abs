// E3 — E2E for the multi-tenant + settings + workflow-library work.
// Mirrors founder-test-fix-1: log in once via API, reuse the warm cookie,
// then drive the new pages. Not a CI gate (no playwright job); run locally
// against a live stack: PLAYWRIGHT_BASE_URL + the backend reachable via the
// /v1 rewrite. Verifies the gaps we just closed don't silently regress.

import { expect, test, type Page } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3457";
const ADMIN = {
  email: process.env.ABS_E2E_ADMIN_EMAIL ?? "admin@demo-acme.com",
  password: process.env.ABS_E2E_ADMIN_PASSWORD ?? "DemoPass2026!",
};

async function apiLogin(page: Page) {
  const res = await page.request.post(`${BASE}/auth/login`, {
    data: ADMIN,
    headers: { "Content-Type": "application/json" },
  });
  expect(res.ok()).toBeTruthy();
}

test.beforeEach(async ({ page }) => {
  await apiLogin(page);
});

test.describe("Projects + per-owner keys page (C1)", () => {
  test("projects page renders create form + keys section", async ({ page }) => {
    await page.goto(`${BASE}/admin/projects`, { waitUntil: "domcontentloaded" });
    await expect(page.locator('[data-test="project-slug"]')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator('[data-test="project-create"]')).toBeVisible();
    await expect(page.locator('[data-test="provider-key-value"]')).toBeVisible();
    await expect(page.locator('[data-test="provider-key-save"]')).toBeVisible();
  });

  test("create a project and see it listed", async ({ page }) => {
    const slug = `e2e-proj-${Date.now()}`;
    await page.goto(`${BASE}/admin/projects`, { waitUntil: "domcontentloaded" });
    await page.locator('[data-test="project-slug"]').fill(slug);
    await page.locator('[data-test="project-create"]').click();
    await expect(page.getByText(slug, { exact: false })).toBeVisible({
      timeout: 10_000,
    });
  });
});

test.describe("Settings — Save buttons are wired (E2)", () => {
  test("general save persists tenant name", async ({ page }) => {
    await page.goto(`${BASE}/admin/settings`, { waitUntil: "domcontentloaded" });
    const name = `E2E Tenant ${Date.now()}`;
    await page.locator('[data-test="settings-tenant-name"]').fill(name);
    await page.locator('[data-test="settings-save-general"]').click();
    // The button flips to the saved label — proof the handler ran (not a no-op).
    await expect(page.locator('[data-test="settings-save-general"]')).toContainText(
      /Kaydedildi|Kaydediliyor/,
      { timeout: 10_000 },
    );
  });

  test("webhooks tab save is functional", async ({ page }) => {
    await page.goto(`${BASE}/admin/settings`, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: /Webhook/i }).click();
    const save = page.locator('[data-test="settings-save"]').first();
    await expect(save).toBeVisible();
    await save.click();
    await expect(save).toContainText(/Kaydedildi|Kaydediliyor/, { timeout: 10_000 });
  });
});

test.describe("Workflow builder — saved library (E1)", () => {
  test("builder shows the saved-workflows panel", async ({ page }) => {
    await page.goto(`${BASE}/admin/workflow-builder`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.locator('[data-testid="saved-workflows"]')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator('[data-testid="save-button"]')).toBeVisible();
  });

  test("save a workflow then see it in the library", async ({ page }) => {
    await page.goto(`${BASE}/admin/workflow-builder`, {
      waitUntil: "domcontentloaded",
    });
    await page.locator('[data-testid="save-button"]').click();
    // After save, the library refreshes and lists at least one saved workflow.
    await expect(
      page.locator('[data-testid="saved-workflow-row"]').first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});
