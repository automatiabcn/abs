// Install the server, then sign in — once, and let every scenario reuse it.
//
// The install is not scaffolding for the suite; it is the first scenario. Every
// spec behind it needs a server where an admin exists, a provider key is in
// place and chat can answer. Something has to make that true, and until now the
// answer was "a backend that happened to have been installed on one laptop
// months ago" — so the suite could only run where the product already worked,
// which is the one place it can tell you nothing. Pointed at an empty server it
// failed at the login form, and the other thirty-three tests never ran.
//
// It goes through the wizard's own screens, typing the key into the field a
// customer types it into, because that is the path being sold and a path that is
// never walked is a path that is broken.
//
// Signing in once is not a speed optimisation either: a login per test tripped
// the 5/minute brute-force cap (which is correct and stays), so the suite failed
// in whichever test happened to be sixth — a moving, meaningless failure that
// hides the real ones. A person signs in once and then works; so does the suite.

import { expect, test as setup } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, login, requireBackend } from "./helpers/stack";

export const ADMIN_STATE = "playwright/.auth/admin.json";

// The wizard is served by the backend — Caddy routes /setup to it in production,
// and the dev frontend does not proxy it — so the browser goes to that origin.
const BACKEND = process.env.ABS_BACKEND_URL ?? "http://127.0.0.1:8000";

// A real key: the scenarios ask the assistant real questions and read the
// answers. A fake one would exercise the error path and report on the product.
const PROVIDER_KEY = process.env.GROQ_API_KEY ?? process.env.ABS_GROQ_API_KEY ?? "";

setup("install the server, then sign in", async ({ page, request }) => {
  await requireBackend(request);

  const status = await (await request.get("/v1/setup/status")).json();

  if (!status.completed) {
    expect(
      PROVIDER_KEY,
      "this suite installs a server from scratch and then asks it a question, so it needs " +
        "a real provider key — export GROQ_API_KEY=... and run it again",
    ).not.toBe("");

    await page.goto(`${BACKEND}/setup`);

    // 1 — the first admin. There is nobody to authenticate as yet; this is the
    // account every scenario behind this one signs in as.
    const admin = page.locator('form[data-step-key="admin"]');

    // Before the address that works, the one that does not. Everybody mistypes
    // an email eventually, and what the product said when they did was, in full,
    // "HTTP 422" — the wizard only knew how to read two of the three shapes its
    // own server replies in. On the first screen, to someone opening an account.
    await admin.locator('input[name="email"]').fill("admin@local");
    await admin.locator('input[name="password"]').fill(ADMIN_PASSWORD);
    await admin.locator('button[type="submit"]').click();
    const errorBox = page.locator("#setup-error");
    await expect(errorBox).toBeVisible();
    await expect(errorBox, "the wizard answered a mistyped email with a status code").not.toContainText(
      /HTTP \d\d\d/,
    );
    await expect(errorBox).toContainText(/email/i);

    await admin.locator('input[name="email"]').fill(ADMIN_EMAIL);
    await admin.locator('input[name="password"]').fill(ADMIN_PASSWORD);
    await admin.locator('button[type="submit"]').click();

    // 2 — the licence, which a person who has not bought anything does not have.
    // The free tier is the default and the box is already ticked.
    await expect(page.locator('section[data-step="2"]')).toBeVisible();
    await expect(page.locator("#setup-skip-license")).toBeChecked();
    await page.locator('form[data-step-key="license"] button[type="submit"]').click();

    // 3 — the domain. A first install is on localhost.
    await expect(page.locator('section[data-step="3"]')).toBeVisible();
    await page.locator('form[data-step-key="domain"] button[type="submit"]').click();

    // 4 — the paid provider, skipped. Nobody pastes an Anthropic key on day one,
    // and the product's promise is that they do not have to.
    await expect(page.locator('section[data-step="4"]')).toBeVisible();
    await expect(page.locator("#setup-skip-paid")).toBeChecked();
    await page.locator('form[data-step-key="anthropic"] button[type="submit"]').click();

    // 5 — the key, typed into the field it is typed into. BYOK walked, not
    // asserted: a moment ago this server had no key, and now it has one.
    await expect(page.locator('section[data-step="5"]')).toBeVisible();
    await page
      .locator('form[data-step-key="providers"] input[name="groq_api_key"]')
      .fill(PROVIDER_KEY);
    await page.locator('form[data-step-key="providers"] button[type="submit"]').click();

    // 6 — the wizard's verdict on itself. It calls the provider it was just
    // given, and says in a sentence whether chat can answer. Trusting it here is
    // the whole point: if this is amber, the product does not work, and every
    // green scenario behind it would be a lie told on top of a broken install.
    await expect(page.locator('section[data-step="6"]')).toBeVisible();
    await page.locator("#setup-run-test").click();
    await expect(
      page.locator(".setup-verdict--ok"),
      "the wizard called the key it had just been given and nothing answered",
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".setup-res .setup-pill--ok")).toHaveCount(1);

    await page.locator(".setup-finish").click();
    await page.waitForURL(/\/login/, { timeout: 30_000 });

    const after = await (await request.get("/v1/setup/status")).json();
    expect(
      after.completed,
      "the wizard said it had finished and the server it just installed disagrees",
    ).toBe(true);
  }

  await login(page);
  await page.context().storageState({ path: ADMIN_STATE });
});
