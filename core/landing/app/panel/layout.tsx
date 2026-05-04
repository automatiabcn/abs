// Q7 Phase C — premium /panel shell: theme + query + sidebar + header.
import type { Metadata } from "next";
import type { ReactNode } from "react";

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

export default function PanelLayout({ children }: { children: ReactNode }) {
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
