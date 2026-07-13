/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The icon rail — seven domains, one glance.
//
// The dots are the feature: a domain that needs the operator carries a live
// dot on its icon (approvals waiting → Growth pulses, a provider down →
// Engine turns red). You learn the state of the system from the navigation
// itself, before opening any page. No competitor's rail does this; it is the
// shell's whole argument for existing.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DOMAINS, activeDomain } from "@/components/shell/domains";
import { dotFor } from "@/components/shell/status-dots";
import type { ShellStatus } from "@/components/shell/useShellStatus";
import { cn } from "@/lib/utils";

export function Rail({ status }: { status: ShellStatus }) {
  const pathname = usePathname() ?? "";
  const active = activeDomain(pathname);

  return (
    <nav
      aria-label="Domains"
      data-test="shell-rail"
      className="hidden w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-surface py-2 lg:flex"
    >
      {DOMAINS.map((domain, i) => {
        const Icon = domain.icon;
        const isCurrent = domain.id === active.id;
        const dot = dotFor(domain, status);
        return (
          <span key={domain.id} className="contents">
            <Link
              href={domain.pages[0].href}
              aria-label={domain.label}
              aria-current={isCurrent ? "true" : undefined}
              title={domain.label}
              data-test={`rail-${domain.id}`}
              className={cn(
                "relative grid h-10 w-10 place-items-center rounded transition-colors",
                isCurrent
                  ? "bg-primary-soft text-primary"
                  : "text-subtle hover:bg-surface-raised hover:text-foreground",
              )}
            >
              {isCurrent && (
                <span
                  aria-hidden="true"
                  className="absolute -left-2 top-1/2 h-[18px] w-0.5 -translate-y-1/2 rounded bg-primary"
                />
              )}
              <Icon className="h-[19px] w-[19px]" />
              {dot && (
                <span
                  aria-hidden="true"
                  data-test={`rail-dot-${domain.id}`}
                  className={cn(
                    "absolute right-1.5 top-1.5 h-[6.5px] w-[6.5px] rounded-full border-[1.5px] border-surface",
                    dot === "bad" ? "abs-dot-throb bg-destructive" : "bg-warning",
                  )}
                />
              )}
            </Link>
            {i === 0 && <span aria-hidden="true" className="my-1 h-px w-6 bg-border" />}
          </span>
        );
      })}
    </nav>
  );
}
