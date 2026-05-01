// Q8 / MP1 fix — admin routes get the same chrome as /panel/* so the
// landing nav doesn't double up on auth'd pages (UX_BUGS MT1 + MP1).
import type { ReactNode } from "react";

import { PanelHeader } from "@/components/panel/PanelHeader";
import { PanelSidebar } from "@/components/panel/PanelSidebar";
import { PanelThemeProvider } from "@/components/panel/PanelThemeProvider";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/lib/query-client";

export default function AdminLayout({ children }: { children: ReactNode }) {
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
        <Toaster richColors position="top-right" />
      </QueryProvider>
    </PanelThemeProvider>
  );
}
