/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 *
 * CodeQL js/client-side-unvalidated-url-redirection (#42).
 * Validates the `next` query param against an internal-path allowlist so an
 * attacker cannot craft /login?next=https://evil.tld to phish a logged-in
 * user after a successful POST /auth/login.
 */

const ALLOWED_NEXT_PREFIXES = ["/panel/", "/admin/", "/onboarding"] as const;
const ALLOWED_EXACT = new Set(["/panel", "/admin", "/onboarding"]);
const DEFAULT_NEXT = "/panel";

export function safeRedirect(rawNext: string | null | undefined): string {
  if (!rawNext) return DEFAULT_NEXT;
  if (
    rawNext.startsWith("//") ||
    rawNext.startsWith("http:") ||
    rawNext.startsWith("https:") ||
    rawNext.startsWith("data:") ||
    rawNext.startsWith("javascript:") ||
    rawNext.startsWith("vbscript:") ||
    rawNext.startsWith("file:")
  ) {
    return DEFAULT_NEXT;
  }
  if (!rawNext.startsWith("/")) return DEFAULT_NEXT;
  if (ALLOWED_EXACT.has(rawNext)) return rawNext;
  if (!ALLOWED_NEXT_PREFIXES.some((p) => rawNext.startsWith(p))) {
    return DEFAULT_NEXT;
  }
  return rawNext;
}
