/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/usage`. Server-side fetches the aggregated usage payload from
// /v1/admin/usage with the caller's session cookie and hands it to
// <UsageClient/>, so the first paint shows real numbers.
//
// It used to fall back to a made-up payload when that fetch failed: a 1,000,000
// token Claude budget the operator never set, and `free_path.pct_24h = 1`, which
// the page renders as "100.0 % served free". UsageClient goes out of its way to
// avoid exactly that — `formatPct(null)` prints an em dash rather than invent a
// ratio — and the fallback walked straight past the guard by passing `1`.
//
// This is the page a customer reads to check the product's central cost and
// privacy claim. A failed request must not confirm it.
import { cookies } from "next/headers";
import type { Metadata } from "next";

import UsageClient, { type UsagePayload } from "./UsageClient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Usage — ABS Admin",
  description:
    "Free vs. paid calls, Claude budget spend, calls by provider over the last 24 hours, and the 7-day token trend.",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

async function fetchUsageServerSide(): Promise<{
  usage: UsagePayload | null;
  loadError: string | null;
}> {
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
    if (!res.ok) {
      return { usage: null, loadError: `The server answered ${res.status}.` };
    }
    return { usage: (await res.json()) as UsagePayload, loadError: null };
  } catch (e) {
    return { usage: null, loadError: `The server could not be reached (${String(e)}).` };
  }
}

export default async function UsagePage() {
  const { usage, loadError } = await fetchUsageServerSide();
  return <UsageClient initial={usage} loadError={loadError} />;
}
