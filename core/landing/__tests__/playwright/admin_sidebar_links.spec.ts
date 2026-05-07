// Polish round R2/R3 — every sidebar advertised URL must resolve to a 200
// (after at most one 308 redirect) and no admin-canonical URL may 404.
import { test, expect } from "@playwright/test";

// Mirror of PanelSidebar.tsx NAV — kept inline so the test stays
// self-contained and a sidebar regression flips this list, not a shared
// source we'd have to import through the Next.js bundler.
const SIDEBAR_HREFS = [
  "/panel",
  "/admin/chat",
  "/admin/workflow-builder",
  "/admin/usage",
  "/admin/mcp-tools",
  "/admin/rag",
  "/admin/pipelines",
  "/admin/providers",
  "/admin/marketplace",
  "/panel/quota",
  "/admin/graph",
  "/admin/meetings",
  "/admin/transcription",
  "/admin/settings",
  "/admin/users",
  "/admin/audit",
] as const;

for (const href of SIDEBAR_HREFS) {
  test(`sidebar href ${href} resolves to 200 (no broken link)`, async ({ page }) => {
    const resp = await page.goto(href, { waitUntil: "domcontentloaded" });
    expect(resp, `no response for ${href}`).not.toBeNull();
    // Final status after any redirect chain. 200 OK even if the URL
    // 308'd (e.g. /admin/chat → /panel/chat).
    expect(resp!.status(), `${href} final status`).toBe(200);
  });
}
