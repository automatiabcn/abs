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

  it("renames the cascade item to 'Sağlayıcılar' so the label matches /admin/providers", () => {
    expect(SIDEBAR).toContain('label: "Sağlayıcılar"');
    expect(SIDEBAR).not.toMatch(/label:\s*"Cascade"/);
  });

  it("retains a redirect equivalence map so the active highlight tracks /panel/* landings", () => {
    expect(SIDEBAR).toContain("REDIRECT_EQUIVALENTS");
    expect(SIDEBAR).toContain('"/admin/chat": "/panel/chat"');
  });
});

describe("next.config redirects — admin → panel back-compat", () => {
  it("declares 308 redirects for every short /admin/* the sidebar advertises", () => {
    const required = [
      ['/admin/chat', '/panel/chat'],
      ['/admin/meetings', '/panel/meetings'],
      ['/admin/transcription', '/panel/transcription'],
      ['/admin/mcp-tools', '/panel/tools'],
      ['/admin/cascade', '/admin/providers'],
      ['/admin/dashboard', '/admin/usage'],
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
});
