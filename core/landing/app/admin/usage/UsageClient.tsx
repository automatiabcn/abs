// BUG-V1 — Client island for /admin/usage.
// Renders Tremor metric tiles + 7-day Claude token trend chart.
"use client";

import { useEffect, useState } from "react";
import { AreaChart, Card, ProgressBar } from "@tremor/react";

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
  free_path: { calls_24h: number; pct_24h: number };
  paid_path: { calls_24h: number };
  total_calls_24h: number;
  provider_mix_24h: Record<string, number>;
  daily_trend: Array<{ day: string; claude_tokens: number }>;
};

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)} %`;
}

export default function UsageClient({ initial }: { initial: UsagePayload }) {
  const [data, setData] = useState<UsagePayload>(initial);

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

  const claudePctLabel = formatPct(data.claude.used_pct);
  const freePctLabel = formatPct(data.free_path.pct_24h);
  const trendData = data.daily_trend.map((b) => ({
    date: b.day,
    "Claude tokens": b.claude_tokens,
  }));
  // Polish round R5 — empty axes look broken; surface a friendly message
  // until the first Claude call lands. `every(=== 0)` covers fresh installs
  // and tenants that opted out of Claude.
  const trendIsEmpty =
    trendData.length === 0 ||
    trendData.every((b) => (b["Claude tokens"] ?? 0) === 0);
  const providerRows = Object.entries(data.provider_mix_24h).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <main
      className="mx-auto w-full max-w-6xl px-6 py-10"
      data-test="admin-usage-page"
    >
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Kullanım
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.month} · son 24 saat sağlayıcı dağılımı + 7-günlük Claude token
          trendi.
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
          <p className="text-sm text-muted-foreground">Free path %</p>
          <p className="mt-2 text-3xl font-semibold">{freePctLabel}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {data.free_path.calls_24h} / {data.total_calls_24h} çağrı (24s)
          </p>
        </Card>
        <Card data-test="usage-tile-claude-budget">
          <p className="text-sm text-muted-foreground">Claude budget %</p>
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
            {data.claude.used_tokens.toLocaleString()} /{" "}
            {data.claude.limit_tokens.toLocaleString()} token
          </p>
        </Card>
        <Card data-test="usage-tile-paid-path">
          <p className="text-sm text-muted-foreground">Paid path çağrı (24s)</p>
          <p className="mt-2 text-3xl font-semibold">
            {data.paid_path.calls_24h}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Anthropic / OpenAI opt-in çağrıları.
          </p>
        </Card>
      </section>

      <section className="mt-8" data-test="usage-trend-section">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          7-gün Claude token trendi
        </h2>
        <Card data-test="usage-trend-chart">
          {trendIsEmpty ? (
            <div
              data-test="usage-trend-empty"
              className="flex h-64 flex-col items-center justify-center gap-1 text-center text-sm text-muted-foreground"
            >
              <p className="font-medium text-foreground">
                Henüz Claude çağrısı yok.
              </p>
              <p>İlk çağrıdan sonra trend burada görünecek.</p>
            </div>
          ) : (
            <AreaChart
              className="h-64"
              data={trendData}
              index="date"
              categories={["Claude tokens"]}
              colors={["indigo"]}
              showAnimation
              showLegend={false}
              showGridLines={false}
              curveType="monotone"
              yAxisWidth={48}
            />
          )}
        </Card>
      </section>

      <section className="mt-8" data-test="usage-provider-mix-section">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Sağlayıcı dağılımı (son 24s)
        </h2>
        <Card>
          {providerRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Son 24 saat içinde henüz sağlayıcı çağrısı yok.
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
    </main>
  );
}
