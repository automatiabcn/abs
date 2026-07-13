/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The live strip across the top of the shell. Left to right: identity, the
// failover ring with the provider count, what's waiting on the operator, then
// the command entry and chrome controls. Everything on it is a headline
// number, never a paragraph — the strip is read in a glance between tasks.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, PanelLeftClose, PanelLeftOpen, Search, User } from "lucide-react";

import AbsLogo from "@/components/icons/AbsLogo";
import { FailoverRing } from "@/components/shell/FailoverRing";
import type { ShellStatus } from "@/components/shell/useShellStatus";
import { activeDomain, activePage } from "@/components/shell/domains";
import { ThemeToggle } from "@/components/panel/ThemeToggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent("abs:palette"));
}

interface TopStripProps {
  status: ShellStatus;
  chrome: boolean;
  onToggleChrome: () => void;
}

export function TopStrip({ status, chrome, onToggleChrome }: TopStripProps) {
  const pathname = usePathname() ?? "";
  const domain = activeDomain(pathname);
  const page = activePage(pathname);
  const degraded =
    status.providersUp !== null &&
    status.providersTotal !== null &&
    status.providersUp < status.providersTotal;

  return (
    <div
      data-test="shell-topstrip"
      className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-border bg-surface-raised/90 px-3 text-xs backdrop-blur"
    >
      <Link
        href="/admin/dashboard"
        className="flex shrink-0 items-center gap-2 rounded px-1 py-1"
        aria-label="Overview"
      >
        <AbsLogo size={18} className="text-foreground" />
        <span className="text-[13px] font-semibold tracking-tight text-foreground">ABS</span>
      </Link>

      <span aria-hidden="true" className="h-4 w-px shrink-0 bg-border" />

      <Link
        href="/admin/providers"
        data-test="strip-providers"
        title="Provider chain — one falls, the next takes over"
        className="flex shrink-0 items-center gap-1.5 rounded px-1.5 py-1 text-muted-foreground transition-colors hover:bg-surface"
      >
        <FailoverRing up={status.providersUp} total={status.providersTotal} />
        {status.providersUp !== null && (
          <span className={cn("num-mono font-semibold", degraded ? "text-destructive" : "text-foreground")}>
            {status.providersUp}/{status.providersTotal}
          </span>
        )}
        <span className="hidden sm:inline">providers</span>
      </Link>

      {status.pending !== null && status.pending > 0 && (
        <>
          <span aria-hidden="true" className="hidden h-4 w-px shrink-0 bg-border sm:block" />
          <Link
            href="/admin/approvals"
            data-test="strip-pending"
            className="flex shrink-0 items-center gap-1.5 rounded px-1.5 py-1 text-muted-foreground transition-colors hover:bg-surface"
          >
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warning" />
            <span className="num-mono font-semibold text-foreground">{status.pending}</span>
            <span className="hidden sm:inline">waiting for you</span>
          </Link>
        </>
      )}

      {/* Where am I — domain › page, cheap orientation without a second bar. */}
      <nav
        aria-label="Breadcrumb"
        className="hidden min-w-0 items-center gap-1 text-muted-foreground md:flex"
      >
        <span className="truncate">{domain.label}</span>
        {page && page.label !== domain.label && (
          <>
            <ChevronRight aria-hidden="true" className="h-3 w-3 shrink-0 opacity-50" />
            <span className="truncate font-medium text-foreground">{page.label}</span>
          </>
        )}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          data-test="strip-command"
          onClick={openCommandPalette}
          className="hidden items-center gap-2 rounded border border-border bg-surface px-2.5 py-1.5 text-subtle transition-colors hover:border-primary hover:text-primary sm:flex"
        >
          <Search aria-hidden="true" className="h-3.5 w-3.5" />
          <span>Search or run</span>
          <kbd className="rounded bg-surface-raised px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
            ⌘K
          </kbd>
        </button>
        <button
          type="button"
          data-test="shell-chrome-toggle"
          onClick={onToggleChrome}
          aria-label={chrome ? "Hide navigation panel" : "Show navigation panel"}
          title={chrome ? "Hide panel (⌥\\)" : "Show panel (⌥\\)"}
          className="hidden rounded p-1.5 text-muted-foreground transition-colors hover:bg-surface hover:text-foreground lg:block"
        >
          {chrome ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
        </button>
        <ThemeToggle />
        <Button variant="ghost" size="icon" aria-label="User menu" data-test="user-menu">
          <User className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
