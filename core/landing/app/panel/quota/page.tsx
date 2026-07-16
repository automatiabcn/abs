/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// S20.7 — `/panel/quota` monthly usage bars + 80%/95% markers + 5 min
// auto-refresh.
// Tremor visualisation, Configure CTA per
// provider, summary tiles, terminology unified to "usage".
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  BarChart3,
  Layers,
  Settings,
  Zap,
} from "lucide-react";
import { formatDate, formatNumber } from "@/lib/format";

// Tremor was the panel/quota route's largest
// dependency (~600KB across recharts + tremor chunks). Swap the
// ProgressBar for a 4-line CSS bar (no semantic loss, the original
// only renders a colored width%) and lazy-load DateRangePicker via
// next/dynamic so Tremor only ships when the date picker actually
// mounts.

function LightProgressBar({
  value,
  tone,
  className,
}: {
  value: number;
  tone: "emerald" | "amber" | "rose";
  className?: string;
}) {
  const palette = {
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    rose: "bg-rose-500",
  } as const;
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={`h-2 w-full overflow-hidden rounded-full bg-muted ${className ?? ""}`}
    >
      <div
        className={`h-full transition-[width] duration-500 ${palette[tone]}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface Slice {
  used: number;
  limit: number;
  percent: number;
  label: string;
  configured?: boolean;
}

interface QuotaPayload {
  claude_plus: Slice;
  free_providers: Record<string, Slice>;
  warnings: string[];
  period_start: string;
  period_end: string;
}

const REFRESH_MS = 5 * 60 * 1000;

// The panel is English-first; format through the shared util with an explicit
// locale so a date never renders as an ambiguous "01/07/2026" that depends on
// the viewer's browser locale. Month name removes the day/month ambiguity.
function fmtNumber(n: number): string {
  return formatNumber(n, "en");
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return formatDate(d, "en", { year: "numeric", month: "short", day: "numeric" });
}

function tone(percent: number): "emerald" | "amber" | "rose" {
  if (percent >= 0.95) return "rose";
  if (percent >= 0.8) return "amber";
  return "emerald";
}

function ProviderRow({ slice, name }: { slice: Slice; name: string }) {
  const pct = Math.min(100, slice.percent * 100);
  const t = tone(slice.percent);
  return (
    <li
      data-test="quota-row"
      data-provider={name}
      data-configured={slice.configured ?? true}
      className={cn(
        "rounded-md border border-border bg-card/50 p-3",
        slice.configured === false && "opacity-70",
      )}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-mono text-sm">{slice.label || name}</span>
          {slice.configured === false && (
            <Badge variant="outline" className="text-[10px]">
              not set up
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs">
          {slice.configured === false ? (
            <Link href="/admin/settings" passHref>
              <Button
                variant="outline"
                size="sm"
                data-test="configure-cta"
                className="h-7 text-[11px]"
              >
                <Settings className="mr-1 h-3 w-3" />
                Set up
              </Button>
            </Link>
          ) : (
            <span className="font-mono">
              {fmtNumber(slice.used)} / {fmtNumber(slice.limit)}
            </span>
          )}
        </div>
      </div>
      {slice.configured !== false && (
        <LightProgressBar value={pct} tone={t} className="mt-1" />
      )}
      {slice.percent >= 0.8 && (
        <div className="mt-1 flex items-center gap-1 text-[11px] text-amber-700 dark:text-amber-300">
          <AlertTriangle className="h-3 w-3" />
          {Math.round(slice.percent * 100)}% used — {slice.percent >= 0.95 ? "almost out" : "running low"}
        </div>
      )}
    </li>
  );
}

export default function QuotaPage() {
  const [data, setData] = useState<QuotaPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        // quota_status always reports the current billing period; there is no
        // date-range parameter, so the page shows this month, honestly.
        const res = await fetch("/v1/system/quota_status", {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as QuotaPayload;
        if (active) {
          setData(json);
          setLoading(false);
          setError(null);
        }
      } catch (exc) {
        if (active) {
          // Name what failed instead of a bare "unknown".
          setError(
            `Couldn't load usage: ${exc instanceof Error ? exc.message : "unknown error"}`
          );
          setLoading(false);
        }
      }
    }
    void load();
    const t = window.setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(t);
    };
  }, []);

  const allSlices = data
    ? [["claude_plus", data.claude_plus] as const, ...Object.entries(data.free_providers)]
    : [];

  const totalCalls = allSlices.reduce(
    (sum, [, s]) => sum + (s?.used ?? 0),
    0,
  );
  // 3rd-eye audit — the backend QuotaSlice has no `cost_usd` field, so the old
  // "estimated cost" tile summed undefined → always $0.00. This page tracks
  // rate-limit usage, not spend (cost lives on /admin/usage + billing). The
  // tile now surfaces a real, on-topic signal already in the payload: the
  // count of providers running low.
  const warningCount = data?.warnings?.length ?? 0;
  const configuredCount = allSlices.filter(([, s]) => s?.configured !== false).length;
  const freePathPct =
    allSlices.length > 0
      ? Math.round(
          (allSlices.filter(
            ([n, s]) => n !== "claude_plus" && s?.configured !== false,
          ).length /
            allSlices.length) *
            100,
        )
      : 0;

  return (
    <div
      data-page="panel-quota"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6 flex flex-wrap items-start justify-between gap-4"
      >
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BarChart3 className="h-5 w-5 text-primary" />
            Limits
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data
              ? `Rate-limit usage this period · ${fmtDate(data.period_start)} – ${fmtDate(data.period_end)}`
              : "How much of each provider you have used, and what is running low."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/admin/settings" passHref>
            <Button variant="outline" size="sm">
              <Settings className="mr-2 h-3.5 w-3.5" />
              Provider settings
            </Button>
          </Link>
        </div>
      </motion.header>

      {/* ─── 4 stat tile (QT5 fix) ──────────────────────── */}
      <section
        data-test="quota-stats"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
      >
        {[
          {
            label: "Requests used",
            value: fmtNumber(totalCalls),
            icon: Layers,
            tone: "indigo",
          },
          {
            label: "Running low",
            value: fmtNumber(warningCount),
            icon: AlertTriangle,
            tone: "emerald",
          },
          {
            label: "Providers ready",
            value: `${configuredCount}/${allSlices.length}`,
            icon: Zap,
            tone: "amber",
          },
          {
            label: "Free providers",
            value: `${freePathPct}%`,
            icon: BarChart3,
            tone: "violet",
          },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="bg-card/60">
              <CardContent className="flex items-center gap-3 py-3">
                <Icon className="h-4 w-4 text-primary" />
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    {s.label}
                  </div>
                  <div className="font-mono text-base">{s.value}</div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </section>

      <Card className="bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Providers</CardTitle>
          <CardDescription>
            Amber at 80% used, red at 95%. Providers you haven&apos;t set up yet show a Set up button.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
              {error}
            </div>
          ) : (
            <ul className="space-y-2">
              {data && (
                <>
                  <ProviderRow slice={data.claude_plus} name="claude_plus" />
                  {Object.entries(data.free_providers).map(([name, slice]) => (
                    <ProviderRow key={name} slice={slice} name={name} />
                  ))}
                </>
              )}
            </ul>
          )}
          {data?.warnings.length ? (
            <div
              data-test="quota-warnings"
              className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200"
            >
              <div className="mb-1 flex items-center gap-1 font-semibold">
                <AlertTriangle className="h-3 w-3" />
                Needs attention
              </div>
              <ul className="list-disc space-y-1 pl-4">
                {data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
