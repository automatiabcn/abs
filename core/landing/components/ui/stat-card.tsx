/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// A number an operator reads at a glance, with the one line of context that
// makes it mean something.
//
// The panel had these everywhere as ad-hoc divs, each picking its own colour
// from the raw palette (rose-500 here, emerald-600 there) so "bad" looked
// different on every page. Tone is a fixed vocabulary now — neutral, good,
// warn, bad — and it maps to semantic tokens, never to the brand accent. A
// figure that needs attention should read as such before anyone parses the
// digits.
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatTone = "neutral" | "good" | "warn" | "bad";

const TONE_TEXT: Record<StatTone, string> = {
  neutral: "text-foreground",
  good: "text-success",
  warn: "text-warning",
  bad: "text-destructive",
};

const TONE_ICON: Record<StatTone, string> = {
  neutral: "text-subtle",
  good: "text-success",
  warn: "text-warning",
  bad: "text-destructive",
};

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon: Icon,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: StatTone;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div
      data-tone={tone}
      className={cn(
        "flex flex-col gap-1 rounded border border-border bg-surface p-4",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="mono text-[10px] font-medium uppercase tracking-wider text-subtle">
          {label}
        </span>
        {Icon && <Icon className={cn("h-4 w-4 shrink-0", TONE_ICON[tone])} />}
      </div>
      <span
        className={cn(
          "num-mono text-2xl font-semibold tracking-tight",
          TONE_TEXT[tone],
        )}
      >
        {value}
      </span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}
