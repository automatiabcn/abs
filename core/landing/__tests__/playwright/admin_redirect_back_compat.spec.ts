// Polish round R2/R3 — short admin URLs that don't host their own page
// must server-redirect (308) to the live route. Verifies bookmarks for
// /admin/cascade etc. don't dead-end on a 404.
import { test, expect } from "@playwright/test";

const REDIRECTS: Array<{ from: string; to: string }> = [
  { from: "/admin/chat", to: "/panel/chat" },
  { from: "/admin/meetings", to: "/panel/meetings" },
  { from: "/admin/transcription", to: "/panel/transcription" },
  { from: "/admin/mcp-tools", to: "/panel/tools" },
  { from: "/admin/cascade", to: "/admin/providers" },
  { from: "/admin/dashboard", to: "/admin/usage" },
];

for (const { from, to } of REDIRECTS) {
  test(`${from} redirects to ${to}`, async ({ page }) => {
    const resp = await page.goto(from, { waitUntil: "domcontentloaded" });
    expect(resp, `no response for ${from}`).not.toBeNull();
    expect(resp!.status(), `${from} final status`).toBe(200);
    expect(page.url(), `${from} did not land on ${to}`).toContain(to);
  });
}
