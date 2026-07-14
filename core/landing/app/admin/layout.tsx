/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 / MP1 fix — admin routes get the same chrome as /panel/* so the
// landing nav doesn't double up on auth'd pages (UX_BUGS MT1 + MP1).
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Cmdk palette deferred via the same client shim
// used by /panel/layout.tsx.
import CommandPalette from "@/components/panel/CommandPaletteLazy";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
import { AppShell } from "@/components/shell/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/lib/query-client";

export const metadata: Metadata = {
  description:
    "ABS Server admin console — manage providers, pipelines, RAG, plugins, users and the audit log.",
  robots: { index: false, follow: false },
};

// Fail-closed restore.
// Middleware (middleware.ts) already gates /admin/* on cookie + /auth/me,
// but a repro showed `docker compose stop backend` left /admin/*
// returning 200 + cached HTML. Defense-in-depth: SSR layout itself
// probes /healthz before rendering chrome. Backend down → /login banner.
const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

async function _probeBackendHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/healthz`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// Page-level RBAC gate. middleware.ts only checks "logged in" (/auth/me), so
// without this a non-admin member loads the admin chrome.
//
// This used to end in `} catch { return true; }` — fail-OPEN. The comment
// defended it as "a transient hiccup must never lock out a real admin", but the
// hiccup it opened the door on was a 2.5-second timeout, and the door was the
// whole console: users, audit log, providers, keys. An attacker who can slow one
// request down by two and a half seconds — or simply a busy server — got in.
//
// A gate that opens when it cannot tell is not a gate. So:
//   • a definitive answer decides it (200 → admin, 401/403 → denied);
//   • anything else — a timeout, a 500, a network error — is *unknown*, and
//     unknown does not render the console. It says so, and offers a retry.
// A real admin sees a page telling them to try again. That is a far smaller cost
// than the alternative, and unlike the alternative it is one they can see.
type AdminVerdict = "admin" | "denied" | "unverified";

async function _adminVerdict(): Promise<AdminVerdict> {
  try {
    const cookieHeader = (await cookies()).toString();
    const res = await fetch(`${BACKEND_URL}/v1/admin/me`, {
      cache: "no-store",
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
      signal: AbortSignal.timeout(2500),
    });
    if (res.ok) return "admin";
    if (res.status === 401 || res.status === 403) return "denied";
    return "unverified";
  } catch {
    return "unverified";
  }
}

function Notice({ title, body }: { title: string; body: string }) {
  return (
    <main
      data-test="admin-gate-notice"
      className="flex min-h-[70vh] flex-col items-center justify-center gap-4 bg-background p-6 text-center text-foreground"
    >
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="max-w-md text-sm text-muted-foreground">{body}</p>
      <a
        href="/login"
        className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent"
      >
        Go to sign-in
      </a>
    </main>
  );
}

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const healthy = await _probeBackendHealthy();
  if (!healthy) {
    redirect("/login?reason=backend-unreachable");
  }
  const verdict = await _adminVerdict();
  if (verdict === "denied") {
    // Inline notice (no redirect → no loop for a logged-in non-admin).
    return (
      <Notice
        title="You need admin access"
        body="This console is for admins only. Ask an admin to change your role, or sign in with an admin account."
      />
    );
  }
  if (verdict === "unverified") {
    return (
      <Notice
        title="We could not check your access"
        body="The server did not answer in time, so we cannot confirm you are an admin. Reload the page to try again — the console stays closed until we know."
      />
    );
  }
  return (
    <PanelThemeProvider>
      <QueryProvider>
        <AppShell>{children}</AppShell>
        <CommandPalette />
        <Toaster richColors position="top-right" />
      </QueryProvider>
    </PanelThemeProvider>
  );
}
