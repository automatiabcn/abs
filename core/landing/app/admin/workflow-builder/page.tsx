/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { Metadata } from "next";
import { cookies } from "next/headers";

import WorkflowChatPanel from "@/components/WorkflowChatPanel";
import { SAMPLE_WORKFLOW } from "@/lib/workflow";

export const metadata: Metadata = {
  title: "Workflow Builder — ABS Admin",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

// The legacy `x-abs-role` request header was NEVER populated (middleware only
// validates the session, nothing injects the role) — so isAdmin was always
// false and Çalıştır / Kuru çalıştır / Kaydet were permanently disabled for
// everyone. Resolve admin the same way the marketplace page does: an
// authenticated panel user defaults to admin unless /auth/me says otherwise.
async function resolveIsAdmin(): Promise<boolean> {
  try {
    const session = (await cookies()).get("abs_session");
    if (!session?.value) return false;
    const res = await fetch(`${BACKEND_URL}/auth/me`, {
      headers: { cookie: `abs_session=${session.value}` },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return false;
    const me = (await res.json()) as { role?: string } | null;
    return me != null && (me.role === undefined || me.role === "admin");
  } catch {
    return false;
  }
}

export default async function Page() {
  const isAdmin = await resolveIsAdmin();
  return (
    <main className="mx-auto max-w-7xl px-6 py-12">
      <h1 className="text-3xl font-semibold text-zinc-900 dark:text-zinc-50">
        Workflow Builder
      </h1>
      <p className="mt-2 mb-8 max-w-2xl text-zinc-600 dark:text-zinc-300">
        Doğal dilde anlat — ABS, tenant policy kontrolleri ve human-in-the-loop
        kapıları gömülü n8n-uyumlu workflow üretir.
      </p>
      <WorkflowChatPanel initialWorkflow={SAMPLE_WORKFLOW} isAdmin={isAdmin} />
    </main>
  );
}
