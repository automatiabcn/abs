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

// Sprint 21 / Faz D — cmdk palette deferred via the same client shim
// used by /panel/layout.tsx.
import CommandPalette from "@/components/panel/CommandPaletteLazy";
import { PanelHeader } from "@/components/panel/PanelHeader";
import { PanelSidebar } from "@/components/panel/PanelSidebar";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/lib/query-client";

export const metadata: Metadata = {
  description:
    "ABS Server yönetici konsolu — cascade sağlayıcı, pipeline, RAG, marketplace, kullanıcı ve denetim kayıtları yönetimi.",
  robots: { index: false, follow: false },
};

// Sprint 2N FAZ B — UAT-009 fail-closed restore (P0 #2M-025).
// Middleware (middleware.ts) already gates /admin/* on cookie + /auth/me,
// but Sprint 2M repro showed `docker compose stop backend` left /admin/*
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

// Page-level RBAC gate. middleware.ts only checks "logged in" (/auth/me), so a
// non-admin member could load the admin chrome (every data call then 401s —
// backend is secure, but it's a confusing shell). Probe the admin-only
// /v1/admin/me with the caller's cookies: a definitive 401/403 means
// not-an-admin → render an access-denied notice instead of the console.
// Fail-open on network errors so a transient hiccup never locks out a real
// admin (the backend still gates the actual data).
async function _isAdmin(): Promise<boolean> {
  try {
    const cookieHeader = (await cookies()).toString();
    const res = await fetch(`${BACKEND_URL}/v1/admin/me`, {
      cache: "no-store",
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
      signal: AbortSignal.timeout(2500),
    });
    if (res.status === 401 || res.status === 403) return false;
    return true;
  } catch {
    return true;
  }
}

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const healthy = await _probeBackendHealthy();
  if (!healthy) {
    redirect("/login?reason=backend-unreachable");
  }
  const admin = await _isAdmin();
  if (!admin) {
    // Inline notice (no redirect → no loop for a logged-in non-admin).
    return (
      <main className="flex min-h-[70vh] flex-col items-center justify-center gap-4 bg-background p-6 text-center text-foreground">
        <h1 className="text-xl font-semibold">Yönetici yetkisi gerekli</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Bu alan yalnızca yönetici hesapları içindir. Yöneticinizden sizi admin
          yapmasını isteyin ya da bir yönetici hesabıyla giriş yapın.
        </p>
        <a
          href="/login"
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent"
        >
          Giriş sayfası
        </a>
      </main>
    );
  }
  return (
    <PanelThemeProvider>
      <QueryProvider>
        <div className="flex min-h-[calc(100vh-3.5rem)] bg-background text-foreground">
          <PanelSidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <PanelHeader />
            <div className="flex-1 overflow-x-hidden">{children}</div>
          </div>
        </div>
        <CommandPalette />
        <Toaster richColors position="top-right" />
      </QueryProvider>
    </PanelThemeProvider>
  );
}
