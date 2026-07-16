/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Client island for /admin/usage.
// Renders Tremor metric tiles + 7-day Claude token trend chart.
"use client";

import { formatNumber } from "@/lib/format";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Card, ProgressBar } from "@tremor/react";

// Lazy-load the Tremor AreaChart (pulls in recharts ~80KB).
// The empty-state path doesn't need it at all; the chart only mounts when
// `trendData` has at least one non-zero point.
const UsageTrendChart = dynamic(
  () => import("@/components/admin/charts/UsageTrendChart"),
  {
    ssr: false,
    loading: () => (
      <div
        data-test="usage-trend-skeleton"
        className="flex h-64 items-center justify-center text-sm text-muted-foreground"
      >
        Loading…
      </div>
    ),
  },
);

export type UsagePayload = {
  month: string;
  claude: {
    limit_tokens: number;
    used_tokens: number;
    used_pct: number;
    over_warn: boolean;
    over_block: boolean;
    banner: string | null;
  };
  free_path: { calls_24h: number; pct_24h: number | null };
  paid_path: { calls_24h: number };
  total_calls_24h: number;
  provider_mix_24h: Record<string, number>;
  daily_trend: Array<{ day: string; claude_tokens: number }>;
};

function formatPct(v: number | null): string {
  // No traffic yet → no ratio. Show an em dash instead of a fabricated 100 %.
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)} %`;
}

export default function UsageClient({
  initial,
  loadError = null,
}: {
  initial: UsagePayload | null;
  loadError?: string | null;
}) {
  const [data, setData] = useState<UsagePayload | null>(initial);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const r = await fetch("/v1/admin/usage", {
          credentials: "include",
          cache: "no-store",
        });
        if (!r.ok) return;
        const next = (await r.json()) as UsagePayload;
        setData(next);
      } catch {
        // Network blip — keep last good payload.
      }
    }, 30_000);
    return () => clearInterval(t);
  }, []);

  // No numbers is not the same as zero numbers. This page is where a customer
  // checks the product's cost and privacy claim, so a request that failed says
  // it failed — it does not answer the question with a shrug shaped like proof.
  if (!data) {
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-10" data-test="admin-usage-page">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Usage</h1>
        </header>
        <div
          data-test="usage-load-error"
          className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400"
        >
          We could not load your usage. {loadError ?? ""} Nothing here is an estimate —
          reload once the server is reachable.
        </div>
      </div>
    );
  }

  const claudePctLabel = formatPct(data.claude.used_pct);
  const freePctLabel = formatPct(data.free_path.pct_24h);
  const trendData = data.daily_trend.map((b) => ({
    date: b.day,
    "Claude tokens": b.claude_tokens,
  }));
  // empty axes look broken; surface a friendly message
  // until the first Claude call lands. `every(=== 0)` covers fresh installs
  // and tenants that opted out of Claude.
  const trendIsEmpty =
    trendData.length === 0 ||
    trendData.every((b) => (b["Claude tokens"] ?? 0) === 0);
  const providerRows = Object.entries(data.provider_mix_24h).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <div
      className="mx-auto w-full max-w-6xl px-6 py-10"
      data-test="admin-usage-page"
    >
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Usage
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.month} · what your providers handled in the last 24 hours, and
          how much of the Claude budget you have spent.
        </p>
      </header>

      {data.claude.banner ? (
        <div
          role="alert"
          data-test="usage-claude-banner"
          className="mb-6 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
        >
          {data.claude.banner}
        </div>
      ) : null}

      <section
        className="grid grid-cols-1 gap-4 md:grid-cols-3"
        data-test="usage-metric-grid"
      >
        <Card data-test="usage-tile-free-path">
          <p className="text-sm text-muted-foreground">Served free</p>
          <p className="mt-2 text-3xl font-semibold">{freePctLabel}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {data.free_path.calls_24h} of {data.total_calls_24h} calls in the
            last 24h
          </p>
        </Card>
        <Card data-test="usage-tile-claude-budget">
          <p className="text-sm text-muted-foreground">Claude budget used</p>
          <p className="mt-2 text-3xl font-semibold">{claudePctLabel}</p>
          <ProgressBar
            value={Math.min(100, data.claude.used_pct * 100)}
            color={
              data.claude.over_block
                ? "red"
                : data.claude.over_warn
                  ? "amber"
                  : "emerald"
            }
            className="mt-3"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            {formatNumber(data.claude.used_tokens, "en")} of{" "}
            {formatNumber(data.claude.limit_tokens, "en")} tokens
          </p>
        </Card>
        <Card data-test="usage-tile-paid-path">
          <p className="text-sm text-muted-foreground">Paid calls (24h)</p>
          <p className="mt-2 text-3xl font-semibold">
            {data.paid_path.calls_24h}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Calls you opted in to send to Anthropic or OpenAI.
          </p>
        </Card>
      </section>

      <section className="mt-8" data-test="usage-trend-section">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Claude tokens, last 7 days
        </h2>
        <Card data-test="usage-trend-chart">
          {trendIsEmpty ? (
            <div
              data-test="usage-trend-empty"
              className="flex h-64 flex-col items-center justify-center gap-1 text-center text-sm text-muted-foreground"
            >
              <p className="font-medium text-foreground">
                No Claude calls yet.
              </p>
              <p>The trend appears here after the first one.</p>
            </div>
          ) : (
            <UsageTrendChart data={trendData} />
          )}
        </Card>
      </section>

      <section className="mt-8" data-test="usage-provider-mix-section">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Calls by provider (last 24h)
        </h2>
        <Card>
          {providerRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No provider calls in the last 24 hours.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {providerRows.map(([provider, count]) => (
                <li
                  key={provider}
                  className="flex items-center justify-between py-2 text-sm"
                  data-test={`usage-provider-row-${provider}`}
                >
                  <span className="font-mono text-foreground">{provider}</span>
                  <span className="text-muted-foreground">{count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
