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

export function dotFor(domain: ShellDomain, status: ShellStatus): "bad" | null {
  if (domain.status === "approvals") {
    return status.pending !== null && status.pending > 0 ? "bad" : null;
  }
  if (domain.status === "providers") {
    if (status.providersUp === null || status.providersTotal === null) return null;
    return status.providersUp < status.providersTotal ? "bad" : null;
  }
  return null;
}

export function dotDomains(domains: ShellDomain[], status: ShellStatus): Set<string> {
  return new Set(
    domains.filter((domain) => dotFor(domain, status) !== null).map((d) => d.id),
  );
}
