// Q10 Round 3 / L4 — a11y axe-core sweep across the 15 panel surfaces.
// Each surface must report 0 'critical' and 0 'serious' WCAG 2.2 AA
// violations. 'moderate' / 'minor' are surfaced as warnings (test does
// not fail) so the team can triage them in subsequent rounds.

import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

interface Surface {
  slug: string;
  path: string;
}

const SURFACES: Surface[] = [
  { slug: "panel",         path: "/panel" },
  { slug: "chat",          path: "/panel/chat" },
  { slug: "tools",         path: "/panel/tools" },
  { slug: "providers",     path: "/admin/providers" },
  { slug: "pipelines",     path: "/admin/pipelines" },
  { slug: "rag",           path: "/admin/rag" },
  { slug: "marketplace",   path: "/admin/marketplace" },
  { slug: "quota",         path: "/panel/quota" },
  { slug: "graph",         path: "/admin/graph" },
  { slug: "settings",      path: "/admin/settings" },
  { slug: "audit",         path: "/admin/audit" },
  { slug: "users",         path: "/admin/users" },
  { slug: "meetings",      path: "/panel/meetings" },
  { slug: "transcription", path: "/panel/transcription" },
  { slug: "workflow",      path: "/admin/workflow-builder" },
];

async function loginIfNeeded(page: Page) {
  const email = process.env.ABS_PANEL_EMAIL ?? "admin@local";
  const password = process.env.ABS_PANEL_PASSWORD ?? "CHANGEME";
  await page.request
    .post("/auth/login", {
      data: { email, password },
    })
    .catch(() => null);
}

test.describe("Q10/L4 — axe-core WCAG 2.2 AA sweep", () => {
  test.beforeEach(async ({ page }) => {
    await loginIfNeeded(page);
  });

  for (const s of SURFACES) {
    test(`q10-l4 ${s.slug} a11y`, async ({ page }) => {
      const resp = await page.goto(s.path, { waitUntil: "networkidle" });
      expect(resp).not.toBeNull();
      // Auth-redirected pages get scanned in their login form state — that
      // is still a valid a11y target.
      const builder = new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
        .disableRules([
          // Tremor injects color-contrast tokens that vary at runtime;
          // we audit those separately via Lighthouse contrast (Round 5
          // L5). Disable here to avoid false positives on every page.
          "color-contrast",
        ]);

      const result = await builder.analyze();

      const blocking = result.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      const warnings = result.violations.filter(
        (v) => v.impact !== "critical" && v.impact !== "serious",
      );

      // Surface a digestible summary in the test output.
      if (blocking.length > 0) {
        const human = blocking
          .map(
            (v) =>
              `${v.impact} · ${v.id} · ${v.help} (${v.nodes.length} nodes)`,
          )
          .join("\n  ");
        console.error(`✗ ${s.slug} blocking violations:\n  ${human}`);
      }
      if (warnings.length > 0) {
        const human = warnings
          .map((v) => `${v.impact} · ${v.id}: ${v.help}`)
          .join("\n  ");
        console.warn(`⚠ ${s.slug} warnings:\n  ${human}`);
      }

      expect(
        blocking,
        `${s.slug}: ${blocking.length} critical/serious violation(s)`,
      ).toEqual([]);
    });
  }
});
