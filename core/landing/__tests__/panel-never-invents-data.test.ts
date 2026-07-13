/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// A panel that cannot reach its server must say so. It must never fill the gap
// with something that looks like an answer.
//
// This is not a hypothetical. Every server-rendered admin page fetched its data
// with the caller's cookie and, on any failure, returned a fixture instead:
//
//   - /admin/audit rendered five signed-looking entries — a login five minutes
//     ago by admin@demo-acme.com, a vault secret read, each with an hmac
//     fragment — next to a CSV button offering them as GDPR Article 15 / SOC 2
//     evidence. The one page whose entire value is "this is what really
//     happened" was the one fabricating.
//   - /admin/users rendered three colleagues who do not exist, one of them
//     holding admin.
//
// Neither page showed any sign of degradation. The rows were simply there.
//
// The rule this test enforces is narrow and mechanical, because the failure was:
// a server component may not import a fixture and hand it to its client island.
// Empty is fine. A named EMPTY_* constant of zeroes is fine. A plausible row is
// not.

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const APP = join(__dirname, "..", "app");

// stdlib rather than a glob library on purpose: this guard has to survive a
// fresh `npm ci` for as long as the product ships, and a guard that leans on an
// undeclared transitive dependency is one lockfile away from being deleted.
function serverPages(): string[] {
  const out: string[] = [];
  for (const area of ["admin", "panel"]) {
    const root = join(APP, area);
    for (const entry of readdirSync(root, {
      recursive: true,
      withFileTypes: true,
    })) {
      if (entry.isFile() && entry.name === "page.tsx") {
        out.push(join(entry.parentPath ?? entry.path, entry.name));
      }
    }
  }
  return out;
}

describe("the panel never invents data it failed to fetch", () => {
  it("finds the server-rendered pages it is meant to be guarding", () => {
    // If a refactor moves these, the test must fail loudly rather than pass by
    // scanning nothing — a guard that silently guards zero files is worse than
    // no guard, because it reads as a green check.
    const pages = serverPages();
    expect(pages.length).toBeGreaterThan(5);
    expect(pages.some((p) => p.includes("admin/audit"))).toBe(true);
    expect(pages.some((p) => p.includes("admin/users"))).toBe(true);
  });

  it("no server page falls back to a fixture when its fetch fails", () => {
    const offenders: string[] = [];
    for (const page of serverPages()) {
      const src = readFileSync(page, "utf8");
      // Only the import matters. A page cannot render a fixture it never pulled
      // in, and matching the identifier at the import is far harder to fool than
      // scanning the body for `return MOCK_…`.
      const imported = /import\s*{[^}]*\bMOCK_[A-Z_]+\b[^}]*}\s*from/s.test(src);
      if (imported) offenders.push(page.slice(page.indexOf("app/")));
    }
    expect(
      offenders,
      "these pages hand a fabricated fixture to the browser when the server " +
        "cannot be reached — show the failure instead",
    ).toEqual([]);
  });

  it("the audit and users pages ship no fabricated rows at all", () => {
    // Belt to the import brace: the fixtures themselves are gone, so they cannot
    // be reached from anywhere — a client island, a story, a stray re-export.
    for (const area of ["audit", "users"]) {
      const types = readFileSync(join(APP, "admin", area, "types.ts"), "utf8");
      expect(types, `admin/${area}/types.ts still carries a fixture`).not.toMatch(
        /export const MOCK_/,
      );
      // The fixtures were built out of demo-tenant identities. If one comes
      // back by another name, it will almost certainly come back with these.
      expect(types).not.toMatch(/demo-acme|@example\.com/);
    }
  });

  it("both pages have somewhere to put the failure", () => {
    const audit = readFileSync(join(APP, "admin", "audit", "AuditClient.tsx"), "utf8");
    const users = readFileSync(join(APP, "admin", "users", "UsersClient.tsx"), "utf8");
    expect(audit).toContain('data-test="audit-load-error"');
    expect(users).toContain('data-test="users-load-error"');
    // And the audit CSV cannot be exported out of a failed read: a file handed
    // to an auditor must not be able to originate from a page that read nothing.
    expect(audit).toMatch(/disabled={failed}/);
  });
});
