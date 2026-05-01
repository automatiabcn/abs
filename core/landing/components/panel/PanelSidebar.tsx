// Q7 Phase C — premium left navigation rail for /panel + /admin routes.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Boxes,
  LayoutDashboard,
  Mic,
  Store,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/panel", label: "Genel Bakış", icon: LayoutDashboard },
  { href: "/admin/workflow-builder", label: "Workflow", icon: Workflow },
  { href: "/admin/marketplace", label: "Marketplace", icon: Store },
  { href: "/panel/meetings", label: "Toplantılar", icon: Mic },
  { href: "/panel/quota", label: "Kota", icon: BarChart3 },
  { href: "/panel/transcription", label: "Transcription", icon: Boxes },
] as const;

export function PanelSidebar() {
  const pathname = usePathname() ?? "";
  return (
    <aside
      data-test="panel-sidebar"
      className="hidden w-60 shrink-0 border-r border-border bg-card/50 p-4 lg:flex lg:flex-col"
    >
      <div className="mb-8 flex items-center gap-2 px-2">
        <div className="h-8 w-8 rounded-md bg-primary/20 ring-1 ring-primary/30" />
        <div className="flex flex-col leading-tight">
          <span className="font-mono text-sm tracking-tight text-foreground">
            Automatia ABS
          </span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Operator
          </span>
        </div>
      </div>
      <nav className="space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href ||
            (href !== "/panel" && pathname.startsWith(href + "/")) ||
            (href === "/panel" && pathname === "/panel");
          return (
            <Link
              key={href}
              href={href}
              data-active={active}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-md border border-border bg-background/40 p-3 text-[11px] text-muted-foreground">
        <div className="font-mono text-foreground">v1.0.0-rc1</div>
        <div>self-host AI orchestration</div>
      </div>
    </aside>
  );
}
