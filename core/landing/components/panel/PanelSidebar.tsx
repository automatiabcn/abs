// Q7 Phase C — premium left navigation rail for /panel + /admin routes.
// Q8 / MT2 fix — extended to 8 visible items, grouped by category. Items
// for not-yet-shipped Q8 phases (Tools, RAG, Pipelines, Providers, Graph,
// Settings, Audit, Users) are appended as phases land.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Boxes,
  Brain,
  Database,
  LayoutDashboard,
  Layers,
  MessageSquare,
  Mic,
  Settings,
  ShieldCheck,
  Sliders,
  Store,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavGroup = "Üretim" | "Operasyon" | "Toplantılar" | "Yönetim";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  group: NavGroup;
}

const NAV: NavItem[] = [
  // ── Üretim ─────────────────────────────────────
  { href: "/panel", label: "Genel Bakış", icon: LayoutDashboard, group: "Üretim" },
  { href: "/panel/chat", label: "Sohbet", icon: MessageSquare, group: "Üretim" },
  { href: "/admin/workflow-builder", label: "Workflow", icon: Workflow, group: "Üretim" },
  { href: "/panel/tools", label: "MCP Tools", icon: Wrench, group: "Üretim" },
  { href: "/admin/rag", label: "RAG Bilgi Tabanı", icon: Database, group: "Üretim" },
  { href: "/admin/pipelines", label: "Quality Pipelines", icon: Sliders, group: "Üretim" },
  // ── Operasyon ──────────────────────────────────
  { href: "/admin/providers", label: "Cascade", icon: Layers, group: "Operasyon" },
  { href: "/admin/marketplace", label: "Marketplace", icon: Store, group: "Operasyon" },
  { href: "/panel/quota", label: "Kota", icon: BarChart3, group: "Operasyon" },
  { href: "/admin/graph", label: "Knowledge Graph", icon: Brain, group: "Operasyon" },
  // ── Toplantılar ────────────────────────────────
  { href: "/panel/meetings", label: "Toplantılar", icon: Mic, group: "Toplantılar" },
  { href: "/panel/transcription", label: "Transcription", icon: Boxes, group: "Toplantılar" },
  // ── Yönetim ────────────────────────────────────
  { href: "/admin/settings", label: "Ayarlar", icon: Settings, group: "Yönetim" },
  { href: "/admin/users", label: "Kullanıcılar", icon: Users, group: "Yönetim" },
  { href: "/admin/audit", label: "Denetim", icon: ShieldCheck, group: "Yönetim" },
];

const GROUP_ORDER: NavGroup[] = ["Üretim", "Operasyon", "Toplantılar", "Yönetim"];

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
      <nav className="space-y-4">
        {GROUP_ORDER.map((group) => {
          const items = NAV.filter((n) => n.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {group}
              </div>
              <ul className="space-y-1">
                {items.map(({ href, label, icon: Icon }) => {
                  const active =
                    pathname === href ||
                    (href !== "/panel" && pathname.startsWith(href + "/")) ||
                    (href === "/panel" && pathname === "/panel");
                  return (
                    <li key={href}>
                      <Link
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
                    </li>
                  );
                })}
              </ul>
            </div>
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
