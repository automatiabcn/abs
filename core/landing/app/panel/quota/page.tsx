// S20.7 — /panel/quota: monthly usage bars + 80%/95% markers + 5dk auto-refresh
"use client";

import { useEffect, useState } from "react";

interface Slice {
  used: number;
  limit: number;
  percent: number;
  label: string;
  configured?: boolean;  // Q3 P11 — false → gray-disabled row
}

interface QuotaPayload {
  claude_plus: Slice;
  free_providers: Record<string, Slice>;
  warnings: string[];
  period_start: string;
  period_end: string;
}

const REFRESH_MS = 5 * 60 * 1000; // S20.8 — 5dk polling, brief 30s yerine

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

function barColor(percent: number): string {
  if (percent >= 0.95) return "#dc2626"; // rose-600
  if (percent >= 0.8) return "#f59e0b";  // amber-500
  return "#10b981";                       // emerald-500
}

function Bar({ percent }: { percent: number }) {
  const pct = Math.min(100, percent * 100);
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="relative h-2 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800"
    >
      <div
        className="absolute inset-y-0 left-0 transition-[width] duration-500"
        style={{ width: `${pct}%`, background: barColor(percent) }}
      />
      <div
        aria-hidden="true"
        className="absolute inset-y-0 w-px bg-amber-500/60"
        style={{ left: "80%" }}
      />
      <div
        aria-hidden="true"
        className="absolute inset-y-0 w-px bg-rose-500/70"
        style={{ left: "95%" }}
      />
    </div>
  );
}

export default function QuotaPanel() {
  const [data, setData] = useState<QuotaPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const res = await fetch("/v1/system/quota_status", {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = (await res.json()) as QuotaPayload;
        if (!cancelled) {
          setData(payload);
          setUpdatedAt(new Date());
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) setError((exc as Error).message);
      }
    };
    fetchOnce();
    const handle = setInterval(fetchOnce, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, []);

  if (error && !data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="alert" className="text-rose-700 dark:text-rose-300">
          Kota okunamadı: {error}
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12 text-zinc-500">
        Yükleniyor…
      </main>
    );
  }

  const items: Array<{ key: string; slice: Slice }> = [
    { key: "claude_plus", slice: data.claude_plus },
    ...Object.entries(data.free_providers).map(([key, slice]) => ({ key, slice })),
  ];

  return (
    <main
      data-page="panel-quota"
      className="mx-auto max-w-3xl px-6 py-12 text-zinc-900 dark:text-zinc-100"
    >
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Aylık Kullanım</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Periyot {fmtDate(data.period_start)} → {fmtDate(data.period_end)}.
          {updatedAt && ` Son güncelleme: ${updatedAt.toLocaleTimeString("tr-TR")}.`}
        </p>
      </header>

      <section className="space-y-4">
        {items.map(({ key, slice }) => {
          const configured = slice.configured !== false; // Q3 P11
          return (
            <div
              key={key}
              data-provider={key}
              data-configured={configured}
              className={
                "rounded border border-zinc-200 p-3 dark:border-zinc-800 " +
                (configured ? "" : "opacity-50")
              }
            >
              <div className="mb-2 flex items-baseline justify-between text-sm">
                <span className="font-medium">
                  {slice.label}
                  {!configured && (
                    <span className="ml-2 text-xs font-normal text-zinc-500">
                      (yapılandırılmadı)
                    </span>
                  )}
                </span>
                <span className="font-mono text-xs text-zinc-500">
                  {configured
                    ? `${fmtNumber(slice.used)} / ${fmtNumber(slice.limit)} (${Math.round(slice.percent * 100)}%)`
                    : "—"}
                </span>
              </div>
              {configured && <Bar percent={slice.percent} />}
            </div>
          );
        })}
      </section>

      {data.warnings.length > 0 && (
        <section
          aria-live="polite"
          className="mt-6 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950"
        >
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
            Uyarılar
          </h2>
          <ul className="space-y-1 font-mono text-xs">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
