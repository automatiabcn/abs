/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The context panel — the active domain's pages, nothing else.
//
// This is the half of the old sidebar worth keeping: named links for where you
// are. The half not worth keeping was the other six groups stacked above and
// below it. Rows that own a live number (Approvals, Providers) carry it inline,
// so the panel answers "which page changed" the same way the rail answers
// "which domain".
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { activeDomain, isActive } from "@/components/shell/domains";
import type { ShellStatus } from "@/components/shell/useShellStatus";
import { cn } from "@/lib/utils";

function badgeFor(
  href: string,
  status: ShellStatus,
): { text: string; tone: "bad" | "ok" } | null {
  if (href === "/admin/approvals" && status.pending !== null && status.pending > 0) {
    return { text: String(status.pending), tone: "bad" };
  }
  if (href === "/admin/providers" && status.providersUp !== null) {
    const degraded =
      status.providersTotal !== null && status.providersUp < status.providersTotal;
    return {
      text: `${status.providersUp}/${status.providersTotal}`,
      tone: degraded ? "bad" : "ok",
    };
  }
  return null;
}

export function ContextPanel({ status }: { status: ShellStatus }) {
  const pathname = usePathname() ?? "";
  const domain = activeDomain(pathname);

  return (
    <aside
      data-test="shell-context"
      className="hidden w-52 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-border bg-surface-raised px-2.5 py-3.5 lg:flex"
    >
      <div className="px-2 pb-2 font-mono text-[10px] uppercase tracking-[0.1em] text-subtle">
        {domain.label}
      </div>
      {domain.pages.map((page) => {
        const active = isActive(page.href, pathname);
        const badge = badgeFor(page.href, status);
        return (
          <Link
            key={page.href}
            href={page.href}
            data-active={active}
            className={cn(
              "flex items-center justify-between gap-2 rounded px-2 py-[5.5px] text-[13px] transition-colors",
              active
                ? "bg-surface font-medium text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-surface hover:text-foreground",
            )}
          >
            <span className="truncate">{page.label}</span>
            {badge && (
              <span
                className={cn(
                  "num-mono rounded px-1.5 py-px text-[10px]",
                  badge.tone === "bad"
                    ? "bg-destructive-soft text-destructive"
                    : "bg-success-soft text-success",
                )}
              >
                {badge.text}
              </span>
            )}
          </Link>
        );
      })}

      <div className="mt-auto rounded border border-border-soft bg-surface p-2.5 text-[11px] text-muted-foreground">
        <div className="num-mono text-foreground">
          v{process.env.NEXT_PUBLIC_ABS_VERSION ?? "1.0.6"}
        </div>
        <div>Self-hosted · your data stays here</div>
      </div>
    </aside>
  );
}
