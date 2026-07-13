/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// State, in a shape you can read without reading.
//
// Status was previously spelled out in whatever colour the page author reached
// for — 207 rose, 147 emerald and 108 amber utility classes across the panel,
// none of them agreeing on what "degraded" looked like. One vocabulary now, so
// a red pill means the same thing on the providers page as it does in the audit
// log. The dot carries the state as well as the fill, for anyone who does not
// separate red from green.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type PillTone = "neutral" | "good" | "warn" | "bad" | "info" | "brand";

const TONE: Record<PillTone, string> = {
  neutral: "bg-surface-raised text-muted-foreground",
  good: "bg-success-soft text-success",
  warn: "bg-warning-soft text-warning",
  bad: "bg-destructive-soft text-destructive",
  info: "bg-info-soft text-info",
  brand: "bg-primary-soft text-primary",
};

const DOT: Record<PillTone, string> = {
  neutral: "bg-subtle",
  good: "bg-success",
  warn: "bg-warning",
  bad: "bg-destructive",
  info: "bg-info",
  brand: "bg-primary",
};

export function StatusPill({
  children,
  tone = "neutral",
  dot = true,
  className,
}: {
  children: ReactNode;
  tone?: PillTone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium",
        TONE[tone],
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[tone])}
        />
      )}
      {children}
    </span>
  );
}
