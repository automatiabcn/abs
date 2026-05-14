/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q7 Phase C — premium /panel shell: theme + query + sidebar + header.
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { redirect } from "next/navigation";

// Sprint 21 / Faz D — cmdk palette deferred via a client-only shim
// (Server Components can't pass ssr:false to next/dynamic).
import CommandPalette from "@/components/panel/CommandPaletteLazy";
import { PanelHeader } from "@/components/panel/PanelHeader";
import { PanelSidebar } from "@/components/panel/PanelSidebar";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
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

export default async function PanelLayout({ children }: { children: ReactNode }) {
  const healthy = await _probeBackendHealthy();
  if (!healthy) {
    redirect("/login?reason=backend-unreachable");
  }
  return (
    <PanelThemeProvider>
      <QueryProvider>
        <ServiceWorkerRegister />
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
