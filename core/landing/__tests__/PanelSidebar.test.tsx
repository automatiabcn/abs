// Polish round R2 — sidebar URL audit. The component is a pure data
// declaration, so we verify the NAV table + redirect map without needing
// a Next.js page render.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SIDEBAR = readFileSync(
  resolve(__dirname, "../components/panel/PanelSidebar.tsx"),
  "utf-8",
);

const NEXT_CONFIG = readFileSync(
  resolve(__dirname, "../next.config.ts"),
  "utf-8",
);

// Hrefs that would render the legacy /panel/* page directly. Sidebar must
// not advertise these any more — short /admin/* surfaces them via redirect.
const LEGACY_PANEL_HREFS = [
  '"/panel/chat"',
  '"/panel/meetings"',
  '"/panel/transcription"',
  '"/panel/tools"',
];

const EXPECTED_ADMIN_HREFS = [
  '"/admin/chat"',
  '"/admin/meetings"',
  '"/admin/transcription"',
  '"/admin/mcp-tools"',
];

describe("PanelSidebar — canonical URLs", () => {
  it("does not advertise legacy /panel/* URLs in the NAV table", () => {
    for (const legacy of LEGACY_PANEL_HREFS) {
      expect(
        SIDEBAR.includes(`href: ${legacy}`),
        `sidebar still uses legacy href ${legacy}`,
      ).toBe(false);
    }
  });

  it("advertises the four short /admin/* canonical hrefs", () => {
    for (const expected of EXPECTED_ADMIN_HREFS) {
      expect(
        SIDEBAR.includes(`href: ${expected}`),
        `sidebar missing canonical href ${expected}`,
      ).toBe(true);
    }
  });

  // The nav says what a thing is for, never what it is built from. "Cascade" is
  // the mechanism; an operator arrives wanting to see their Providers.
  it("names the providers item after the route, not after the mechanism", () => {
    expect(SIDEBAR).toContain('label: "Providers"');
    expect(SIDEBAR).not.toMatch(/label:\s*"Cascade"/);
  });

  // Twenty-seven items greeted every newcomer at once. Seven now carry the jobs
  // people arrive with; the rest stay one click away under Advanced — present,
  // not deleted. Both halves of that promise are worth holding onto.
  it("keeps the first screen to seven items and hides nothing", () => {
    // Match the array declarations exactly: `const ADVANCED_KEY` sits above them
    // and would otherwise be what a loose split lands on.
    const primary = SIDEBAR.split("const PRIMARY: NavItem[]")[1]?.split("];")[0] ?? "";
    const advanced = SIDEBAR.split("const ADVANCED: NavItem[]")[1]?.split("];")[0] ?? "";

    const count = (block: string) => (block.match(/href:/g) ?? []).length;

    expect(count(primary)).toBe(7);
    expect(count(advanced)).toBeGreaterThanOrEqual(20);
  });

  it("retains a redirect equivalence map so the active highlight tracks /panel/* landings", () => {
    expect(SIDEBAR).toContain("REDIRECT_EQUIVALENTS");
    expect(SIDEBAR).toContain('"/admin/chat": "/panel/chat"');
  });
});

describe("next.config redirects — admin → panel back-compat", () => {
  // /admin/chat, /admin/mcp-tools, /admin/dashboard, /admin/meetings and
  // /admin/transcription now ship as real /admin/* pages (re-exporting the
  // /panel/* client component) — the /panel → /admin Caddy deprecation made a
  // 308 to /panel/* loop forever. Only the /admin/cascade legacy alias redirects.
  it("declares 308 redirects for the short /admin/* surfaces that still need them", () => {
    const required = [
      ['/admin/cascade', '/admin/providers'],
    ];
    for (const [src, dst] of required) {
      const pattern = new RegExp(
        `source:\\s*"${src}"[\\s\\S]*?destination:\\s*"${dst}"[\\s\\S]*?permanent:\\s*true`,
      );
      expect(
        pattern.test(NEXT_CONFIG),
        `next.config missing 308 redirect ${src} → ${dst}`,
      ).toBe(true);
    }
  });

  it("does NOT declare a 308 for short /admin/* hrefs that ship as real pages", () => {
    const realPageSources = ['/admin/chat', '/admin/mcp-tools', '/admin/dashboard', '/admin/meetings', '/admin/transcription'];
    for (const src of realPageSources) {
      const pattern = new RegExp(`source:\\s*"${src}"`);
      expect(
        pattern.test(NEXT_CONFIG),
        `${src} ships as a real page; next.config should not redirect it`,
      ).toBe(false);
    }
  });
});
