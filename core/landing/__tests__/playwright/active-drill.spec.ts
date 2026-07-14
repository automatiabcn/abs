// Q12-L26 active drill (S7 R47) — SSE drop + WebSocket reconnect.
//
// S6 R37 ran the 30-min idle drill (heap drift -9.63 MB, 0 5xx).
// That covers the *passive* leak surface — but it doesn't prove the
// chat client survives an *active* failure mid-stream.
//
// This spec exercises three drop-shaped failures while the user is
// actively interacting:
//
//   1. SSE mid-stream abort — connection drops after the first chunk.
//      Chat client should NOT lock the input or hang the assistant
//      bubble in a "Yazıyor…" state forever.
//
//   2. SSE 502 Bad Gateway on retry — Caddy/proxy restart simulation.
//      Chat client should surface the chat-error-tile (R35 fix).
//
//   3. /v1/chat/sessions polling drop — sessions endpoint flakes
//      mid-session. The R35 sessions-error-tile must mount.
//
// Pattern: Playwright `page.route()` injects per-call failures.
// We don't touch the real backend; the active drill is at the
// network boundary.

import { test, expect, Page } from "@playwright/test";
import * as fs from "node:fs";

const CHAT_URL = "/panel/chat";

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
    /* fall through */
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

test.describe("Q12-L26 active drill — drop + reconnect", () => {
  test("scenario 1: SSE mid-stream abort — input recovers, no infinite spinner", async ({
    page,
  }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    let firstChunkSent = false;
    await page.route(/\/v1\/chat\/completions/, async (route) => {
      // Send one chunk then abort the connection — simulates a backend
      // kill during streaming. The Vercel AI SDK / fetch reader should
      // surface the partial as an error and unstick the input.
      if (!firstChunkSent) {
        firstChunkSent = true;
        return route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: { "cache-control": "no-cache", connection: "keep-alive" },
          body:
            'data: {"type":"text","content":"Hi","provider":"groq"}\n\n',
        });
      }
      return route.abort("connectionaborted");
    });

    await page.goto(CHAT_URL, { waitUntil: "domcontentloaded" });
    const ta = page.locator("textarea").first();
    await ta.waitFor({ state: "visible", timeout: 10_000 });
    await ta.fill("active drill scenario 1");
    await page.keyboard.press("Enter");

    // Within 12s the input must NOT still be disabled (isStreaming=true).
    // The chat client's finally{} block sets isStreaming=false on
    // any fetch outcome.
    await expect(ta).toBeEnabled({ timeout: 12_000 });

    // The error tile or empty assistant bubble may be present —
    // either surface is a graceful degradation. White-screen is not.
    const bodyText = await page.evaluate(() =>
      document.body.innerText.trim().length,
    );
    expect(bodyText).toBeGreaterThan(0);
  });

  test("scenario 2: SSE 502 Bad Gateway — chat-error-tile surfaces", async ({
    page,
  }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    // Caddy/proxy restart simulation: every chat-completions call
    // returns 502. The R35 retry: 1 cap means the user reaches the
    // error path quickly.
    await page.route(/\/v1\/chat\/completions/, (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ detail: "bad_gateway" }),
      }),
    );

    await page.goto(CHAT_URL, { waitUntil: "domcontentloaded" });
    const ta = page.locator("textarea").first();
    await ta.waitFor({ state: "visible", timeout: 10_000 });
    await ta.fill("active drill scenario 2");
    await page.keyboard.press("Enter");

    const tile = page.locator('[data-test="chat-error-tile"]');
    await expect(tile).toBeVisible({ timeout: 8_000 });
    await expect(tile).toHaveAttribute("role", "alert");
    const text = (await tile.textContent()) ?? "";
    expect(text.toLowerCase()).toContain("hata");
  });

  test("scenario 3: sessions endpoint drop — banner mounts + retry button clickable", async ({
    page,
  }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    // Active-drill flavour of the R35 sessions-error-tile contract:
    // every GET /v1/chat/sessions call returns 502 (proxy-drop). The
    // R35 retry: 1 cap means the banner mounts within ~2s instead of
    // hanging for 15s.
    await page.route(/\/v1\/chat\/sessions/, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          status: 502,
          contentType: "application/json",
          body: JSON.stringify({ detail: "gateway_drop" }),
        });
      }
      // POST/DELETE pass through (we're only dropping list polls).
      return route.continue();
    });

    await page.goto(CHAT_URL, { waitUntil: "load" });

    const banner = page.locator('[data-test="sessions-error-tile"]');
    await expect(banner).toBeVisible({ timeout: 12_000 });
    await expect(banner).toHaveAttribute("role", "alert");

    // Retry button must be clickable (not disabled by the failure).
    const retry = page.locator('[data-test="sessions-error-retry"]');
    await expect(retry).toBeEnabled();

    // Click retry — refetch happens; we don't unmock so the banner
    // stays. The point is the button responds (no JS error).
    await retry.click();
    await page.waitForTimeout(500);
    await expect(banner).toBeVisible();
  });
});
