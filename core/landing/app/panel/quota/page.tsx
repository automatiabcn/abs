/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// S20.7 — `/panel/quota` monthly usage bars + 80%/95% markers + 5dk
// auto-refresh.
// Q8 / QT1+QT2+QT5+QT6 — Tremor visualisation, Configure CTA per
// provider, Total Cost summary tile, terminology unified to "Kota".
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
import dynamic from "next/dynamic";

// Sprint 21 / Faz B — Tremor was the panel/quota route's largest
// dependency (~600KB across recharts + tremor chunks). Swap the
// ProgressBar for a 4-line CSS bar (no semantic loss, the original
// only renders a colored width%) and lazy-load DateRangePicker via
// next/dynamic so Tremor only ships when the date picker actually
// mounts.
const QuotaDateRangePicker = dynamic(
  () => import("@/components/panel/charts/QuotaDateRangePicker"),
  {
    ssr: false,
    loading: () => (
      <div className="h-9 w-72 animate-pulse rounded-md bg-muted" />
    ),
  },
);

// Mirror Tremor's optional shape so the wrapper component types align.
type DateRangePickerValue = { from?: Date; to?: Date };

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

function fmtNumber(n: number): string {
  return n.toLocaleString("tr-TR");
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("tr-TR");
  } catch {
    return iso;
  }
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
              yapılandırılmadı
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
                Yapılandır
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
        <div className="mt-1 flex items-center gap-1 text-[11px] text-amber-300">
          <AlertTriangle className="h-3 w-3" />
          {Math.round(slice.percent * 100)}% — eşik {slice.percent >= 0.95 ? "kritik" : "uyarı"}
        </div>
      )}
    </li>
  );
}

function defaultRange(): DateRangePickerValue {
  // Last 30 days, both ends inclusive.
  const to = new Date();
  const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000);
  return { from, to };
}

export default function QuotaPage() {
  const [data, setData] = useState<QuotaPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Q9 / QT3 — date range filter (presets via Tremor)
  const [range, setRange] = useState<DateRangePickerValue>(defaultRange());

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const params = new URLSearchParams();
        if (range.from) params.set("from", range.from.toISOString().slice(0, 10));
        if (range.to) params.set("to", range.to.toISOString().slice(0, 10));
        const url =
          "/v1/system/quota_status" +
          (params.toString() ? `?${params.toString()}` : "");
        const res = await fetch(url, {
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
          // Q11-L16-002: TR prefix + drop the bare "unknown" EN string.
          setError(
            `Kota verisi yüklenemedi: ${exc instanceof Error ? exc.message : "bilinmeyen hata"}`
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
  }, [range.from, range.to]);

  const allSlices = data
    ? [["claude_plus", data.claude_plus] as const, ...Object.entries(data.free_providers)]
    : [];

  const totalCalls = allSlices.reduce(
    (sum, [, s]) => sum + (s?.used ?? 0),
    0,
  );
  // 3rd-eye audit — the backend QuotaSlice has no `cost_usd` field, so the old
  // "Tahmini maliyet" tile summed undefined → always $0.00. Quota tracks
  // rate-limit usage, not spend (cost lives on /admin/usage + billing). The
  // tile now surfaces a real, on-topic signal already in the payload: the
  // count of active threshold warnings.
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
    <main
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
            Kota
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data
              ? `${fmtDate(data.period_start)} – ${fmtDate(data.period_end)} dönemi`
              : "Sağlayıcı kullanımı, eşik uyarıları, free-path oranı."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <QuotaDateRangePicker
            value={range}
            onValueChange={setRange}
            data-test="quota-date-range"
            enableSelect
            className="w-[22rem] max-w-full"
          />
          <Link href="/admin/settings" passHref>
            <Button variant="outline" size="sm">
              <Settings className="mr-2 h-3.5 w-3.5" />
              Sağlayıcı ayarları
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
            label: "Toplam çağrı",
            value: fmtNumber(totalCalls),
            icon: Layers,
            tone: "indigo",
          },
          {
            label: "Eşik uyarısı",
            value: fmtNumber(warningCount),
            icon: AlertTriangle,
            tone: "emerald",
          },
          {
            label: "Aktif sağlayıcı",
            value: `${configuredCount}/${allSlices.length}`,
            icon: Zap,
            tone: "amber",
          },
          {
            label: "Free-path",
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
          <CardTitle className="text-base">Sağlayıcı kullanımı</CardTitle>
          <CardDescription>
            80% sarı, 95% kırmızı eşik. Yapılandırılmamış sağlayıcılar Configure CTA gösterir.
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
              Kota bilgisi yüklenemedi: {error}
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
                Uyarılar
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
    </main>
  );
}
