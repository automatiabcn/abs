/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// One place decides when a domain's dot lights up; the desktop rail and the
// mobile bar both read it. Two copies of "is Growth urgent?" would drift, and
// a dot that shows on the phone but not the desktop reads as a bug in the
// product's honesty, not just in its CSS.
import type { ShellDomain } from "@/components/shell/domains";
import type { ShellStatus } from "@/components/shell/useShellStatus";

export type DotTone = "bad" | "warn";

export function dotFor(domain: ShellDomain, status: ShellStatus): DotTone | null {
  if (domain.status === "approvals") {
    return status.pending !== null && status.pending > 0 ? "bad" : null;
  }
  if (domain.status === "providers") {
    if (status.providersUp === null || status.providersTotal === null) return null;
    return status.providersUp < status.providersTotal ? "bad" : null;
  }
  if (domain.status === "quota") {
    if (status.quotaWorstPct === null) return null;
    if (status.quotaWorstPct >= 100) return "bad";
    return status.quotaWorstPct >= 80 ? "warn" : null;
  }
  return null;
}

export function dotDomains(
  domains: ShellDomain[],
  status: ShellStatus,
): Map<string, DotTone> {
  const map = new Map<string, DotTone>();
  for (const domain of domains) {
    const tone = dotFor(domain, status);
    if (tone) map.set(domain.id, tone);
  }
  return map;
}
