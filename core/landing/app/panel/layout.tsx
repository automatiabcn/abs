// Q7 Phase C — premium /panel shell: theme + query + sidebar + header.
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { CommandPalette } from "@/components/panel/CommandPalette";
import { PanelHeader } from "@/components/panel/PanelHeader";
import { PanelSidebar } from "@/components/panel/PanelSidebar";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
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
