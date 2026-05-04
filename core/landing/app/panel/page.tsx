// R70 (S8) — Sprint 22 RSC Phase C: split-shell for /panel home.
//
// Server-side fetches the three first-paint endpoints in parallel
// (`/v1/panel/tools`, `/v1/system/quota_status`,
// `/v1/panel/cascade/recent`) with the caller's session cookie
// forwarded, hands the payloads to <PanelHomeClient> as
// `initial{Tools,Quota,Cascade}`. The client island uses each as
// React Query `initialData` so the four StatCards (MCP Tools,
// Cascade 24h, Claude Kotası, Sağlayıcılar) and the role="alert"
// banner have data on the very first paint instead of shipping
// "…" placeholders that swap in after hydration.
//
// On any auth/transport failure each fetch falls back to MOCK
// independently — the page never 500s on /panel because of a
// downstream blip. Same fallback semantics as the pre-R70 client
// `useQuery` (no MOCK fallback before, but isError caused the same
// banner to fire — preserved).
import { cookies } from "next/headers";

import PanelHomeClient from "./PanelHomeClient";
import {
  MOCK_CASCADE,
  MOCK_QUOTA,
  MOCK_TOOLS,
  type CascadeResponse,
  type QuotaResponse,
  type ToolsResponse,
} from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

async function fetchSlice<T>(path: string, fallback: T): Promise<T> {
  try {
    const cookieStore = await cookies();
    const cookieHeader = cookieStore
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");

    const res = await fetch(`${BACKEND_URL}${path}`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      cache: "no-store",
    });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export default async function PanelHome() {
  // Three calls in parallel — same waterfall the old client useQuery
  // produced post-hydration, but co-located with render so it's part
  // of the response rather than three round-trips after first paint.
  const [initialTools, initialQuota, initialCascade] = await Promise.all([
    fetchSlice<ToolsResponse>("/v1/panel/tools", MOCK_TOOLS),
    fetchSlice<QuotaResponse>("/v1/system/quota_status", MOCK_QUOTA),
    fetchSlice<CascadeResponse>("/v1/panel/cascade/recent", MOCK_CASCADE),
  ]);

  return (
    <PanelHomeClient
      initialTools={initialTools}
      initialQuota={initialQuota}
      initialCascade={initialCascade}
    />
  );
}
