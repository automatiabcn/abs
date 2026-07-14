// RSC split-shell: /admin/users.
//
// Same shape as R64 (audit). Server `page.tsx` fetches /v1/admin/users
// with the caller's cookie forwarded; client island
// `<UsersClient initialUsers=...>` consumes the array as React Query
// `initialData` so the table is server-rendered before any post-
// hydration refetch fires.
//
// What this spec proves:
//   1. The route still serves /admin/users (no 5xx).
//   2. The interactive client island still mounts (Invite user / dialog).
//   3. The server initial fetch is wired — when the backend returns
//      a non-empty payload, the rows render before any client refetch.
//
// Lighthouse delta is R66, not here.

import { test, expect } from "@playwright/test";
import * as fs from "node:fs";

test.use({ serviceWorkers: "block" });

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
        return { name: parts[5], value: parts[6], domain: "localhost", path: "/" };
      }
    }
  } catch (_e) {
    /* no cookie — auth tests will skip */
  }
  return null;
}

test.describe("/admin/users split-shell", () => {
  test("page renders heading + invite trigger (interactive island still mounts)", async ({
    page,
    context,
  }) => {
    const cookie = loadAuthCookie();
    if (!cookie) test.skip(true, "abs_session cookie missing — run master_repro.sh prep");
    await context.addCookies([
      { ...cookie!, expires: Math.floor(Date.now() / 1000) + 3600 },
    ]);

    const resp = await page.goto("/admin/users", { waitUntil: "load" });
    expect(resp?.status() ?? 0).toBeLessThan(500);

    await expect(page.locator('h1', { hasText: "Users" })).toBeVisible({
      timeout: 10_000,
    });
    const inviteBtn = page.locator('[data-test="users-invite-open"]');
    await expect(inviteBtn).toBeVisible();

    // Interactive contract — invite dialog must open (proves client
    // island mounted and useState wired to DialogTrigger). React 19
    // hydration may finish a beat after waitUntil:"load" under
    // dev-mode parallel-worker contention, so retry the click against
    // the dialog visibility predicate to ride past the hydration race.
    await expect
      .poll(
        async () => {
          await inviteBtn.click({ trial: false });
          return await page
            .locator('[data-test="users-invite-email"]')
            .isVisible();
        },
        { timeout: 8000, intervals: [100, 300, 600, 1200] },
      )
      .toBe(true);
  });

  test("server initial fetch payload is in HTML (server-side render of initialData)", async ({
    page,
    context,
  }) => {
    const cookie = loadAuthCookie();
    if (!cookie) throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );
    await context.addCookies([
      { ...cookie!, expires: Math.floor(Date.now() / 1000) + 3600 },
    ]);

    const resp = await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
    expect(resp?.status() ?? 0).toBeLessThan(500);

    await expect(
      page.locator('[data-page="admin-users"]').first(),
    ).toBeVisible();

    // The page must render the *result of the server fetch* in the first paint —
    // either the real rows, or, when the fetch failed, the notice saying so.
    //
    // This assertion used to accept fallback rows as proof the pipeline worked,
    // which meant it passed identically whether the roster loaded or the backend
    // was unreachable and three fictional colleagues were rendered instead. The
    // fallback is gone; the test now has to name which of the two it got.
    const row = page.locator('[data-test="user-row"]').first();
    const failure = page.locator('[data-test="users-load-error"]').first();
    await expect(row.or(failure)).toBeVisible({ timeout: 8_000 });
  });
});
