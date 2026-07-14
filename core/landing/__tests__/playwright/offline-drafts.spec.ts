// IndexedDB draft persistence + offline mode.
//
// R36 SW caches *responses*; R48 ships the matching *user-input*
// persistence layer. Three guarantees:
//
//   1. Type a draft, reload — draft restores from IndexedDB.
//   2. Go offline (`context.setOffline(true)`), type, reload offline
//      draft survives the offline window.
//   3. Clear the draft (saveDraft("")) — IndexedDB record is deleted
//      so a fresh visitor doesn't inherit a previous user's text.

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

async function clearDraft(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await new Promise<void>((resolve) => {
      const req = indexedDB.deleteDatabase("abs-chat-drafts");
      req.onsuccess = () => resolve();
      req.onerror = () => resolve();
      req.onblocked = () => resolve();
    });
  });
}

test.describe("offline drafts (R48)", () => {
  test("draft restores after a normal reload", async ({ page }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    await page.goto(CHAT_URL, { waitUntil: "load" });
    await clearDraft(page);

    // Re-mount so the (now-empty) cold-mount restore does NOT clobber.
    await page.goto(CHAT_URL, { waitUntil: "load" });
    const ta = page.locator("textarea").first();
    await ta.waitFor({ state: "visible", timeout: 10_000 });

    const draft = "R48 draft persists — reload me";
    await ta.fill(draft);
    // Give the saveDraft useEffect a beat to flush.
    await page.waitForTimeout(400);

    await page.reload({ waitUntil: "load" });
    const ta2 = page.locator("textarea").first();
    await ta2.waitFor({ state: "visible", timeout: 10_000 });
    // Cold mount restore: poll up to 3s for the draft to land.
    await expect(ta2).toHaveValue(draft, { timeout: 3_000 });

    await clearDraft(page);
  });

  test("draft survives an offline window", async ({ page, context }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    await page.goto(CHAT_URL, { waitUntil: "load" });
    await clearDraft(page);
    await page.goto(CHAT_URL, { waitUntil: "load" });

    const ta = page.locator("textarea").first();
    await ta.waitFor({ state: "visible", timeout: 10_000 });

    // Drop the network, type, reload — IndexedDB writes work offline.
    await context.setOffline(true);
    const offlineDraft = "offline draft — network is dead";
    await ta.fill(offlineDraft);
    await page.waitForTimeout(400);

    // Reading IndexedDB while offline must work.
    const stored = await page.evaluate(async () => {
      const db = await new Promise<IDBDatabase | null>((resolve) => {
        const req = indexedDB.open("abs-chat-drafts", 1);
        req.onerror = () => resolve(null);
        req.onsuccess = () =>
          resolve((req as IDBOpenDBRequest).result);
      });
      if (!db) return null;
      return await new Promise<string>((resolve) => {
        const tx = db.transaction("drafts", "readonly");
        const r = tx.objectStore("drafts").get("current");
        r.onerror = () => resolve("");
        r.onsuccess = () =>
          resolve(typeof r.result === "string" ? r.result : "");
      });
    });
    expect(stored).toBe(offlineDraft);

    await context.setOffline(false);
    await clearDraft(page);
  });

  test("clearing the draft deletes the IndexedDB record", async ({
    page,
  }) => {
    if (!(await ensureAuthed(page)))
      throw new Error(
        "could not sign in (no abs_session cookie) — this used to skip itself, " +
          "which made the suite greenest exactly when login was most broken",
      );

    await page.goto(CHAT_URL, { waitUntil: "load" });
    const ta = page.locator("textarea").first();
    await ta.waitFor({ state: "visible", timeout: 10_000 });

    await ta.fill("temporary draft");
    await page.waitForTimeout(400);

    // Clear the input — saveDraft("") should delete the record.
    await ta.fill("");
    await page.waitForTimeout(400);

    const stored = await page.evaluate(async () => {
      const db = await new Promise<IDBDatabase | null>((resolve) => {
        const req = indexedDB.open("abs-chat-drafts", 1);
        req.onerror = () => resolve(null);
        req.onsuccess = () =>
          resolve((req as IDBOpenDBRequest).result);
      });
      if (!db) return "missing-db";
      return await new Promise<string>((resolve) => {
        const tx = db.transaction("drafts", "readonly");
        const r = tx.objectStore("drafts").get("current");
        r.onerror = () => resolve("error");
        r.onsuccess = () =>
          resolve(typeof r.result === "string" ? r.result : "deleted");
      });
    });
    expect(stored).toBe("deleted");
  });
});
