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
// When the fetch fails, this page shows that it failed. It used to fall back to
// a set of sample rows — plausible actors, fresh timestamps, hmac-looking
// strings — which on *this* page is the worst possible answer: the whole promise
// of an audit log is that it is a record of what really happened, and the CSV
// button next to it offers the rows up as GDPR Article 15 / SOC 2 evidence. A
// page that invents entries when it cannot reach the server is not a degraded
// audit log, it is a fabricated one. Empty and honest, or nothing.
import { cookies } from "next/headers";

import AuditClient from "./AuditClient";
import type { AuditEntry } from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// SWEEP — unique <title> per panel/admin page.
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Audit — ABS Admin",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

interface AuditLoad {
  entries: AuditEntry[];
  loadError: string | null;
}

async function fetchAuditServerSide(): Promise<AuditLoad> {
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
    if (!res.ok) {
      return { entries: [], loadError: `The server answered ${res.status}.` };
    }
    const data = await res.json();
    if (Array.isArray(data)) return { entries: data as AuditEntry[], loadError: null };
    if (data && Array.isArray((data as { entries?: unknown }).entries)) {
      return { entries: (data as { entries: AuditEntry[] }).entries, loadError: null };
    }
    return { entries: [], loadError: "The server sent back a reply we could not read." };
  } catch {
    return { entries: [], loadError: "The server could not be reached." };
  }
}

export default async function AuditPage() {
  const { entries, loadError } = await fetchAuditServerSide();
  return <AuditClient initialEntries={entries} loadError={loadError} />;
}
