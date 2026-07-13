/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q7 Phase C — premium /panel shell: theme + query + sidebar + header.
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Sprint 21 / Faz D — cmdk palette deferred via a client-only shim
// (Server Components can't pass ssr:false to next/dynamic).
import CommandPalette from "@/components/panel/CommandPaletteLazy";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
import { AppShell } from "@/components/shell/AppShell";
import ServiceWorkerRegister from "@/components/panel/ServiceWorkerRegister";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/lib/query-client";

export const metadata: Metadata = {
  description:
    "ABS Server admin paneli — cascade sağlayıcılar, MCP araçları, RAG ingest ve kota izleme tek bir self-hosted yüzeyde.",
  robots: { index: false, follow: false },
};

// Sprint 2N FAZ B — UAT-009 fail-closed SSR probe (P0 #2M-025).
// Twin of /admin/layout.tsx — defense-in-depth against cached HTML / SW
// fallback paths that bypass middleware. Backend unreachable → /login.
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

// Page-level RBAC gate — twin of /admin/layout.tsx. Blocks non-admins from the
// panel chrome (backend already 401s the data; this avoids a confusing shell).
// Fail-open on network errors so a transient hiccup never locks out an admin.
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

export default async function PanelLayout({ children }: { children: ReactNode }) {
  const healthy = await _probeBackendHealthy();
  if (!healthy) {
    redirect("/login?reason=backend-unreachable");
  }
  if (!(await _isAdmin())) {
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
        <ServiceWorkerRegister />
        <AppShell>{children}</AppShell>
        <CommandPalette />
        <Toaster richColors position="top-right" />
      </QueryProvider>
    </PanelThemeProvider>
  );
}
