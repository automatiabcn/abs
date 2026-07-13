/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The shell's navigation contract, asserted at the data level.
//
// Successor to PanelSidebar.test.tsx: the 27-route table moved from a flat
// sidebar into components/shell/domains.ts (7 domains + rail + context panel).
// Every promise the old test held is re-held here — canonical /admin/* URLs,
// no legacy /panel/* hrefs, purpose-named labels — plus the new structural
// ones: seven domains, no route lost in the move, no duplicate hrefs.
import { describe, expect, it } from "vitest";

import {
  DOMAINS,
  REDIRECT_EQUIVALENTS,
  activeDomain,
  isActive,
} from "@/components/shell/domains";

const ALL_PAGES = DOMAINS.flatMap((domain) => domain.pages);
const ALL_HREFS = ALL_PAGES.map((page) => page.href);

// The full route table the old 27-item sidebar advertised. The redesign's
// promise was "nothing removed, only regrouped" — this list is that promise.
const LEGACY_SIDEBAR_ROUTES = [
  "/admin/dashboard",
  "/admin/chat",
  "/admin/rag",
  "/admin/meetings",
  "/admin/growth",
  "/admin/usage",
  "/admin/settings",
  "/admin/approvals",
  "/admin/agents",
  "/admin/workflows",
  "/admin/leads",
  "/admin/graph-context",
  "/admin/inbound",
  "/admin/connectors",
  "/admin/transcription",
  "/admin/mcp-tools",
  "/admin/mcp-servers",
  "/admin/mcp-tokens",
  "/admin/pipelines",
  "/admin/providers",
  "/admin/provider-keys",
  "/admin/quota",
  "/admin/graph",
  "/admin/marketplace",
  "/admin/projects",
  "/admin/users",
  "/admin/audit",
];

describe("shell domains — structure", () => {
  it("groups the panel into seven domains", () => {
    expect(DOMAINS).toHaveLength(7);
  });

  it("keeps every route the old sidebar had — nothing removed in the regroup", () => {
    const missing = LEGACY_SIDEBAR_ROUTES.filter(
      (href) => !ALL_HREFS.includes(href),
    );
    expect(missing).toEqual([]);
  });

  it("advertises no href twice", () => {
    expect(new Set(ALL_HREFS).size).toBe(ALL_HREFS.length);
  });

  it("gives every domain at least one page and an icon", () => {
    for (const domain of DOMAINS) {
      expect(domain.pages.length).toBeGreaterThan(0);
      expect(domain.icon).toBeTruthy();
    }
  });
});

describe("shell domains — canonical URLs", () => {
  it("advertises only /admin/* canonical hrefs, never legacy /panel/*", () => {
    const legacy = ALL_HREFS.filter((href) => href.startsWith("/panel"));
    expect(legacy).toEqual([]);
  });

  it("keeps the redirect map so the active highlight follows a 308", () => {
    // /admin/chat 308s to /panel/chat today; standing on the landing URL must
    // still light up the Chat row.
    expect(isActive("/admin/chat", "/panel/chat")).toBe(true);
    expect(isActive("/admin/dashboard", "/panel")).toBe(true);
    // And every mapped key must be a route the shell actually advertises.
    for (const key of Object.keys(REDIRECT_EQUIVALENTS)) {
      expect(ALL_HREFS).toContain(key);
    }
  });
});

describe("shell domains — language", () => {
  it("names things for what they do, not the mechanism", () => {
    const labels = ALL_PAGES.map((page) => page.label);
    expect(labels).toContain("Providers");
    expect(labels).not.toContain("Cascade");
    expect(labels).toContain("Company memory");
    expect(labels).toContain("Quality control");
  });

  it("speaks one language (English) — no bilingual mix on the first screen", () => {
    // The Turkish-specific characters that marked the old mixed nav.
    const turkish = /[çğıöşüÇĞİÖŞÜ]/;
    for (const page of ALL_PAGES) {
      expect(turkish.test(page.label), `label "${page.label}" looks Turkish`).toBe(false);
    }
    for (const domain of DOMAINS) {
      expect(turkish.test(domain.label), `domain "${domain.label}" looks Turkish`).toBe(false);
    }
  });
});

describe("shell domains — live status wiring", () => {
  it("marks Growth with the approvals signal and Engine with providers", () => {
    const growth = DOMAINS.find((domain) => domain.id === "growth");
    const engine = DOMAINS.find((domain) => domain.id === "engine");
    expect(growth?.status).toBe("approvals");
    expect(engine?.status).toBe("providers");
  });

  it("resolves the active domain from any page inside it", () => {
    expect(activeDomain("/admin/approvals").id).toBe("growth");
    expect(activeDomain("/admin/mcp-tools/some-tool").id).toBe("engine");
    expect(activeDomain("/nowhere").id).toBe("overview");
  });
});
