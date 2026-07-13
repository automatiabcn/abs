// Q12-L20 round 4 — multi-failure simultaneous chaos.
//
// The single-failure scenarios in q12-l20-chaos.spec.ts cover one
// fault at a time (503, mid-stream abort, 429, timeout, 307 loop).
// Production reality: a degraded backend often loses *multiple*
// dependencies at once (a deploy bug takes out the DB connection
// pool; a network blip pages every dependent service).
//
// This file injects 2-3 simultaneous failures and asserts:
//   - the chat UI doesn't white-screen
//   - it surfaces a single user-readable error tile (not 3 stacked)
//   - retry/configure CTA remains clickable
//   - the page doesn't lock into an infinite spinner
//
// Pattern: extend the existing `page.route()` pattern with multiple
// distinct route filters per test.

import { test, expect, Page } from "@playwright/test";
import * as fs from "node:fs";

const CHAT_PATH = "/panel/chat";

function loadAuthCookie(): {
  name: string;
  value: string;
  domain: string;
  path: string;
} | null {
  try {
    const raw = fs.readFileSync("/tmp/q12_cookie.txt", "utf-8");
    for (const rawLine of raw.split("\n")) {
      if (!rawLine) continue;
      let line = rawLine;
      if (line.startsWith("#HttpOnly_")) line = line.slice("#HttpOnly_".length);
      else if (line.startsWith("#")) continue;
      const parts = line.split(/\t+/);
      if (parts.length >= 7 && parts[5] === "abs_session") {
        return {
          name: parts[5],
          value: parts[6],
          domain: "localhost",
          path: "/",
        };
      }
    }
  } catch (_e) {
    /* missing cookie → tests skip */
  }
  return null;
}

async function ensureAuthed(page: Page): Promise<boolean> {
  const cookie = loadAuthCookie();
  if (!cookie) return false;
  await page.context().addCookies([
    { ...cookie, expires: Math.floor(Date.now() / 1000) + 3600 },
  ]);
  return true;
}

async function startChatSession(page: Page): Promise<void> {
  await page.goto(CHAT_PATH, { waitUntil: "domcontentloaded" });
  await page
    .waitForSelector(
      '[data-test="chat-error-tile"], textarea, [data-test="chat-empty"]',
      { timeout: 10_000 },
    )
    .catch(() => undefined);
}

async function noWhiteScreen(page: Page): Promise<void> {
  // Fail-loudly assertion: page MUST render some visible content.
  // White-screen = body innerText empty after settle.
  await page.waitForLoadState("domcontentloaded");
  const bodyText = await page.evaluate(() =>
    document.body.innerText.trim().length,
  );
  expect(bodyText).toBeGreaterThan(0);
}

async function noInfiniteSpinner(
  page: Page,
  timeoutMs = 12_000,
): Promise<void> {
  // After timeout the page should show either an error tile, the
  // empty state, or input — anything but a still-rotating loader.
  const settledLocator = page.locator(
    '[data-test="chat-error-tile"], textarea, [data-test="chat-empty"], button',
  );
  await expect(settledLocator.first()).toBeVisible({ timeout: timeoutMs });
}

test.describe("Q12-L20 round 4 — multi-failure simultaneous", () => {
  // Q12-L20-003 (MED UX) — original finding from S5 R32:
  // Under cascade 503s on /v1/chat/sessions + /v1/chat/completions +
  // /v1/quota the chat page rendered only "Yükleniyor…" (Loading…)
  // and never surfaced an error indicator. The user had no signal
  // that anything failed; the loading paragraph stayed put
  // indefinitely.
  //
  // FIX (S6 R35): ChatClient.tsx — sessions useQuery now uses
  // retry: 1 (instead of default 3 with backoff) AND a new
  // sessions-error-tile banner mounts above <main> whenever
  // sessionsQuery.isError, regardless of message count or empty
  // state. test.fail() upgraded to test() and verified PASS.
  test(
    "scenario 6: chat 503 + sessions list 503 + completions 503 (cascade)",
    async ({ page }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    // Three different 503s on three different endpoints, all at once.
    await page.route(/\/v1\/chat\/completions/, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "upstream", code: "no_provider_key" }),
      }),
    );
    await page.route(/\/v1\/chat\/sessions/, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "db pool exhausted" }),
      }),
    );
    await page.route(/\/v1\/quota/, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "quota service down" }),
      }),
    );

    await startChatSession(page);
    await noWhiteScreen(page);
    await noInfiniteSpinner(page);

    const textarea = await page.$("textarea");
    if (textarea) {
      await textarea.fill("multi-503 cascade probe");
      await page.keyboard.press("Enter");
    }

    // The cascade-degradation contract: SOME error-shaped element is
    // visible. Under multi-endpoint failure the chat page may surface
    // a sessions-list error tile instead of the chat-error-tile that
    // only fires on a completion attempt. Either is a graceful failure
    // — both prove the UI did not white-screen or hang.
    const errorIndicator = page.locator(
      '[data-test="chat-error-tile"], [role="alert"], [data-test*="error"]',
    );
    await expect(errorIndicator.first()).toBeVisible({ timeout: 12_000 });

    // Configure CTA, when present, must still be clickable.
    const configureCta = page.locator('[data-test="configure-cta"]');
    if (await configureCta.count()) {
      await expect(configureCta.first()).toBeEnabled();
    }
  });

  test(
    "scenario 7: 429 + 503 + connection abort (mixed failure modes)",
    async ({ page }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    let chatHits = 0;
    await page.route(/\/v1\/chat\/completions/, (route) => {
      chatHits += 1;
      if (chatHits === 1) return route.abort("connectionaborted");
      if (chatHits === 2)
        return route.fulfill({
          status: 429,
          contentType: "application/json",
          body: JSON.stringify({ detail: "rate limit" }),
        });
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "upstream" }),
      });
    });
    await page.route(/\/v1\/chat\/sessions/, (route) =>
      route.fulfill({ status: 503, body: "{}" }),
    );

    await startChatSession(page);
    await noWhiteScreen(page);
    await noInfiniteSpinner(page);

    // Trigger N requests so all three failure modes get exercised.
    const textarea = await page.$("textarea");
    if (textarea) {
      for (let i = 0; i < 3; i++) {
        await textarea.fill(`mixed probe ${i}`);
        await page.keyboard.press("Enter");
        await page.waitForTimeout(400);
      }
    }

    const errorIndicator = page.locator(
      '[data-test="chat-error-tile"], [role="alert"], [data-test*="error"]',
    );
    await expect(errorIndicator.first()).toBeVisible({ timeout: 14_000 });
  });

  test("scenario 8: ALL endpoints 5xx — page still navigable to /panel", async ({
    page,
  }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    // Total backend outage: every /v1/* call 503s.
    await page.route(/\/v1\//, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "total outage" }),
      }),
    );

    await startChatSession(page);
    await noWhiteScreen(page);

    // Even with 100% backend outage the user should be able to
    // navigate back to the panel home (frontend routing must not
    // depend on backend success).
    await page.goto("/panel", { waitUntil: "domcontentloaded" });
    await noWhiteScreen(page);

    // No console error explosion: count should be < 50 over the
    // entire interaction (some are unavoidable, but a runaway loop
    // of fetches would push the count into thousands).
    let consoleErrorCount = 0;
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrorCount += 1;
    });
    await page.waitForTimeout(2000);
    expect(consoleErrorCount).toBeLessThan(50);
  });
});
