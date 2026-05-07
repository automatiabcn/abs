/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// R64 (S8) — Sprint 22 RSC Phase B leg 1: split-shell for /admin/audit.
//
// Server-side fetches the initial 200 audit entries with the caller's
// session cookie forwarded, hands the array to <AuditClient> as
// `initialEntries`, and the client island uses it as React Query
// `initialData` so the first paint already renders rows.
//
// LCP target on slow 3G: ~−400 ms vs the previous client-only shape
// (eliminates the post-hydration round-trip to /v1/admin/audit/recent).
//
// On any auth/transport failure the server falls back to MOCK_AUDIT —
// same behaviour as the pre-R64 client `fetchAudit`.
import { cookies } from "next/headers";

import AuditClient from "./AuditClient";
import { MOCK_AUDIT, type AuditEntry } from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// FOUNDER_FIX_1 / SWEEP — unique <title> per panel/admin page.
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Denetim — ABS Admin",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

async function fetchAuditServerSide(): Promise<AuditEntry[]> {
  try {
    const cookieStore = await cookies();
    const cookieHeader = cookieStore
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");

    const res = await fetch(`${BACKEND_URL}/v1/admin/audit/recent?limit=200`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      cache: "no-store",
    });
    if (!res.ok) return MOCK_AUDIT;
    const data = await res.json();
    if (Array.isArray(data)) return data as AuditEntry[];
    if (data && Array.isArray((data as { entries?: unknown }).entries)) {
      return (data as { entries: AuditEntry[] }).entries;
    }
    return MOCK_AUDIT;
  } catch {
    return MOCK_AUDIT;
  }
}

export default async function AuditPage() {
  const initialEntries = await fetchAuditServerSide();
  return <AuditClient initialEntries={initialEntries} />;
}
