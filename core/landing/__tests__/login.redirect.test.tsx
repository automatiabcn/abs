/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 *
 * Sprint 2D ITEM-2.4 — CodeQL js/client-side-unvalidated-url-redirection (#42).
 * `safeRedirect()` enforces an ALLOWED_NEXT_PREFIXES whitelist so an attacker
 * cannot craft /login?next=https://evil.tld to phish a logged-in user.
 */
import { describe, it, expect } from "vitest";
import { safeRedirect } from "../app/login/safeRedirect";

describe("safeRedirect (open-redirect guard)", () => {
  it("returns default for null/empty input", () => {
    expect(safeRedirect(null)).toBe("/panel");
    expect(safeRedirect("")).toBe("/panel");
    expect(safeRedirect(undefined)).toBe("/panel");
  });

  it("rejects external https origin", () => {
    expect(safeRedirect("https://evil.tld/phish")).toBe("/panel");
    expect(safeRedirect("https://attacker.com")).toBe("/panel");
  });

  it("rejects protocol-relative URL", () => {
    expect(safeRedirect("//evil.tld/x")).toBe("/panel");
  });

  it("rejects javascript: and data: URIs", () => {
    expect(safeRedirect("javascript:alert(1)")).toBe("/panel");
    expect(safeRedirect("data:text/html,<script>alert(1)</script>")).toBe("/panel");
    expect(safeRedirect("vbscript:evil()")).toBe("/panel");
    expect(safeRedirect("file:///etc/passwd")).toBe("/panel");
  });

  it("rejects relative paths not in allowlist", () => {
    expect(safeRedirect("/etc/passwd")).toBe("/panel");
    expect(safeRedirect("/api/secret")).toBe("/panel");
    expect(safeRedirect("/random/page")).toBe("/panel");
  });

  it("rejects paths without leading slash", () => {
    expect(safeRedirect("panel/meetings")).toBe("/panel");
    expect(safeRedirect("../admin")).toBe("/panel");
  });

  it("accepts /panel/* relative paths", () => {
    expect(safeRedirect("/panel/meetings")).toBe("/panel/meetings");
    expect(safeRedirect("/panel/chat")).toBe("/panel/chat");
    expect(safeRedirect("/panel")).toBe("/panel");
  });

  it("accepts /admin/* relative paths", () => {
    expect(safeRedirect("/admin/dashboard")).toBe("/admin/dashboard");
    expect(safeRedirect("/admin/providers")).toBe("/admin/providers");
    expect(safeRedirect("/admin")).toBe("/admin");
  });

  it("accepts /onboarding paths", () => {
    expect(safeRedirect("/onboarding")).toBe("/onboarding");
    expect(safeRedirect("/onboarding/step-2")).toBe("/onboarding/step-2");
  });

  it("rejects schemes with similar prefixes", () => {
    expect(safeRedirect("https:/panel/meetings")).toBe("/panel");
    expect(safeRedirect("http:/panel")).toBe("/panel");
  });
});
