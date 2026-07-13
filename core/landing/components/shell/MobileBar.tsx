/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Mobile navigation: a floating bottom bar, not a hamburger.
//
// One-handed reach decides everything on a phone, and the thumb lives at the
// bottom (the same finding that moved Vercel's mobile nav there in Feb 2026).
// Four domain slots + search; the remaining domains sit one tap away in a
// bottom sheet. The Growth slot keeps its live dot — triage is exactly what a
// phone session is for.
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal, Search } from "lucide-react";

import { DOMAINS, activeDomain } from "@/components/shell/domains";
import { dotDomains } from "@/components/shell/status-dots";
import { openCommandPalette } from "@/components/shell/TopStrip";
import type { ShellStatus } from "@/components/shell/useShellStatus";
import { cn } from "@/lib/utils";

const BAR_SLOTS = ["overview", "assistant", "growth"] as const;

export function MobileBar({ status }: { status: ShellStatus }) {
  const pathname = usePathname() ?? "";
  const active = activeDomain(pathname);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Close the sheet on every route change — a nav tap must land, not linger.
  useEffect(() => {
    setSheetOpen(false);
  }, [pathname]);

  const barDomains = BAR_SLOTS.map(
    (id) => DOMAINS.find((d) => d.id === id)!,
  );
  const sheetDomains = DOMAINS.filter(
    (d) => !BAR_SLOTS.includes(d.id as (typeof BAR_SLOTS)[number]),
  );
  const dots = dotDomains(DOMAINS, status);

  return (
    <>
      {sheetOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          aria-hidden="true"
          onClick={() => setSheetOpen(false)}
        />
      )}

      {/* Bottom sheet with the domains that didn't fit the bar. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="More domains"
        data-test="shell-mobile-sheet"
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-border bg-surface px-4 pb-6 pt-2.5 shadow-lg transition-transform duration-300 lg:hidden",
          sheetOpen ? "translate-y-0" : "translate-y-full",
        )}
      >
        <div aria-hidden="true" className="mx-auto mb-3 h-1 w-9 rounded-full bg-border" />
        {sheetDomains.map((domain) => {
          const Icon = domain.icon;
          return (
            <Link
              key={domain.id}
              href={domain.pages[0].href}
              onClick={() => setSheetOpen(false)}
              className="flex items-center gap-3 rounded px-1.5 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface-raised hover:text-foreground"
            >
              <Icon className="h-4 w-4 text-subtle" />
              {domain.label}
              {dots.has(domain.id) && (
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-destructive" />
              )}
            </Link>
          );
        })}
      </div>

      {/* The floating bar itself. */}
      <div
        data-test="shell-mobile-bar"
        className="fixed inset-x-3 bottom-3 z-50 flex items-center justify-between rounded-full border border-border bg-surface px-2 py-1.5 shadow-lg lg:hidden"
      >
        {barDomains.slice(0, 2).map((domain) => (
          <BarButton
            key={domain.id}
            domain={domain}
            active={active.id === domain.id}
            dot={dots.has(domain.id)}
          />
        ))}

        <button
          type="button"
          onClick={openCommandPalette}
          data-test="mobile-command"
          className="flex min-w-0 flex-1 items-center gap-1.5 px-2 text-xs text-subtle"
        >
          <Search aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Search or run</span>
        </button>

        <BarButton
          domain={barDomains[2]}
          active={active.id === barDomains[2].id}
          dot={dots.has(barDomains[2].id)}
        />

        <button
          type="button"
          aria-label="More"
          aria-expanded={sheetOpen}
          data-test="mobile-more"
          onClick={() => setSheetOpen((open) => !open)}
          className={cn(
            "grid h-8 w-10 place-items-center rounded-full text-subtle transition-colors",
            (sheetOpen || DOMAINS.filter((d) => !BAR_SLOTS.includes(d.id as never)).some((d) => d.id === active.id)) &&
              "bg-primary-soft text-primary",
          )}
        >
          <MoreHorizontal className="h-[17px] w-[17px]" />
        </button>
      </div>
    </>
  );
}

function BarButton({
  domain,
  active,
  dot,
}: {
  domain: (typeof DOMAINS)[number];
  active: boolean;
  dot: boolean;
}) {
  const Icon = domain.icon;
  return (
    <Link
      href={domain.pages[0].href}
      aria-label={domain.label}
      aria-current={active ? "true" : undefined}
      className={cn(
        "relative grid h-8 w-10 place-items-center rounded-full transition-colors",
        active ? "bg-primary-soft text-primary" : "text-subtle",
      )}
    >
      <Icon className="h-[17px] w-[17px]" />
      {dot && (
        <span
          aria-hidden="true"
          className="absolute right-1 top-0.5 h-1.5 w-1.5 rounded-full bg-destructive"
        />
      )}
    </Link>
  );
}
