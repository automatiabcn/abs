// BUG-V1 — `/admin/usage` widget. Server-side fetches the aggregated
// usage payload from /v1/admin/usage with the caller's session cookie,
// hands it to <UsageClient/> as initialData so the first paint shows
// real numbers (no client-only spinner round-trip).
//
// On transport failure the server falls back to a zero payload with
// the dense 7-day trend so the page stays usable.
import { cookies } from "next/headers";
import type { Metadata } from "next";

import UsageClient, { type UsagePayload } from "./UsageClient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Kullanım — ABS Admin",
  description:
    "Free path / Claude bütçe kullanımı, son 24 saat sağlayıcı dağılımı ve 7-günlük token trend.",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

function emptyTrend(): UsagePayload["daily_trend"] {
  const today = new Date();
  return Array.from({ length: 7 }, (_, idx) => {
    const offset = 6 - idx;
    const d = new Date(today);
    d.setUTCDate(today.getUTCDate() - offset);
    return { day: d.toISOString().slice(0, 10), claude_tokens: 0 };
  });
}

function fallback(): UsagePayload {
  return {
    month: new Date().toISOString().slice(0, 7),
    claude: {
      limit_tokens: 1_000_000,
      used_tokens: 0,
      used_pct: 0,
      over_warn: false,
      over_block: false,
      banner: null,
    },
    free_path: { calls_24h: 0, pct_24h: 1 },
    paid_path: { calls_24h: 0 },
    total_calls_24h: 0,
    provider_mix_24h: {},
    daily_trend: emptyTrend(),
  };
}

async function fetchUsageServerSide(): Promise<UsagePayload> {
  try {
    const cookieStore = await cookies();
    const cookieHeader = cookieStore
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");
    const res = await fetch(`${BACKEND_URL}/v1/admin/usage`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      cache: "no-store",
    });
    if (!res.ok) return fallback();
    return (await res.json()) as UsagePayload;
  } catch {
    return fallback();
  }
}

export default async function UsagePage() {
  const initial = await fetchUsageServerSide();
  return <UsageClient initial={initial} />;
}
