/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Split-shell for the /panel home route.
//
// Server-side fetches the three first-paint endpoints in parallel
// (`/v1/panel/tools`, `/v1/system/quota_status`,
// `/v1/panel/cascade/recent`) with the caller's session cookie
// forwarded, hands the payloads to <PanelHomeClient> as
// `initial{Tools,Quota,Cascade}`. The client island uses each as
// React Query `initialData` so the four StatCards (tools, answers
// today, Claude usage, providers) and the role="alert"
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
  EMPTY_CASCADE,
  EMPTY_QUOTA,
  EMPTY_TOOLS,
  type CascadeResponse,
  type QuotaResponse,
  type ToolsResponse,
} from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// SWEEP — every panel/admin page now ships a unique <title>
// so tester walkthroughs and OS window titles can disambiguate routes.
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Overview — ABS Panel",
  robots: { index: false, follow: false },
};

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
    fetchSlice<ToolsResponse>("/v1/panel/tools", EMPTY_TOOLS),
    fetchSlice<QuotaResponse>("/v1/system/quota_status", EMPTY_QUOTA),
    fetchSlice<CascadeResponse>("/v1/panel/cascade/recent", EMPTY_CASCADE),
  ]);

  return (
    <PanelHomeClient
      initialTools={initialTools}
      initialQuota={initialQuota}
      initialCascade={initialCascade}
    />
  );
}
