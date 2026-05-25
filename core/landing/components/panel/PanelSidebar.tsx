/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

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
  // Sprint 2B BUG-19 — Genel Bakış now lands on the new /admin/dashboard
  // route (5-source aggregated overview) instead of /panel home.
  { href: "/admin/dashboard", label: "Genel Bakış", icon: LayoutDashboard, group: "Üretim" },
  // Sprint 2B BUG-20 — /admin/chat is now a real page (not a 308 to
  // /panel/chat). Same for /admin/mcp-tools and /admin/quota below.
  { href: "/admin/chat", label: "Sohbet", icon: MessageSquare, group: "Üretim" },
  { href: "/admin/workflow-builder", label: "Workflow", icon: Workflow, group: "Üretim" },
  // BUG-V1 — /admin/usage Free path % + Claude budget % widget.
  { href: "/admin/usage", label: "Kullanım", icon: BarChart3, group: "Üretim" },
  { href: "/admin/mcp-tools", label: "MCP Tools", icon: Wrench, group: "Üretim" },
  { href: "/admin/rag", label: "RAG Bilgi Tabanı", icon: Database, group: "Üretim" },
  { href: "/admin/pipelines", label: "Quality Pipelines", icon: Sliders, group: "Üretim" },
  // ── Operasyon ──────────────────────────────────
  // Polish round R2 — label aligned with route ("Sağlayıcılar" not "Cascade").
  { href: "/admin/providers", label: "Sağlayıcılar", icon: Layers, group: "Operasyon" },
  { href: "/admin/marketplace", label: "Marketplace", icon: Store, group: "Operasyon" },
  // Sprint 2B BUG-25 — /admin/quota is the canonical kota route now.
  { href: "/admin/quota", label: "Kota", icon: BarChart3, group: "Operasyon" },
  { href: "/admin/graph", label: "Knowledge Graph", icon: Brain, group: "Operasyon" },
  // ── Toplantılar ────────────────────────────────
  { href: "/admin/meetings", label: "Toplantılar", icon: Mic, group: "Toplantılar" },
  { href: "/admin/transcription", label: "Transcription", icon: Boxes, group: "Toplantılar" },
  // ── Yönetim ────────────────────────────────────
  { href: "/admin/settings", label: "Ayarlar", icon: Settings, group: "Yönetim" },
  { href: "/admin/users", label: "Kullanıcılar", icon: Users, group: "Yönetim" },
  { href: "/admin/audit", label: "Denetim", icon: ShieldCheck, group: "Yönetim" },
];

const GROUP_ORDER: NavGroup[] = ["Üretim", "Operasyon", "Toplantılar", "Yönetim"];

// Polish round R4 — CSS `text-transform: uppercase` runs in the document
// locale (English by default) and turns Turkish "i" into dotless "I"
// instead of "İ". Pre-render the labels with `toLocaleUpperCase("tr-TR")`
// and drop the CSS transform so the dotted İ comes through verbatim.
const GROUP_LABEL_TR: Record<NavGroup, string> = {
  "Üretim": "Üretim".toLocaleUpperCase("tr-TR"),
  "Operasyon": "Operasyon".toLocaleUpperCase("tr-TR"),
  "Toplantılar": "Toplantılar".toLocaleUpperCase("tr-TR"),
  "Yönetim": "Yönetim".toLocaleUpperCase("tr-TR"),
};

// Polish round R2 — sidebar advertises /admin/* but a few pages still
// resolve to /panel/* via next.config redirects (308). Map both ways so the
// active highlight tracks the user wherever the redirect lands them.
//
// Sprint 2B BUG-19/20/25/26 — chat / mcp-tools / quota / dashboard are
// now real /admin/* pages (no redirect). The /panel/* equivalents are
// kept here so a user who deep-links to a legacy URL still gets the
// matching sidebar highlight.
const REDIRECT_EQUIVALENTS: Record<string, string> = {
  "/admin/chat": "/panel/chat",
  "/admin/meetings": "/panel/meetings",
  "/admin/transcription": "/panel/transcription",
  "/admin/mcp-tools": "/panel/tools",
  "/admin/quota": "/panel/quota",
  "/admin/dashboard": "/panel",
  "/admin/cascade": "/admin/providers",
};

function isActive(href: string, pathname: string): boolean {
  if (pathname === href) return true;
  if (pathname.startsWith(href + "/")) return true;
  const live = REDIRECT_EQUIVALENTS[href];
  if (live && (pathname === live || pathname.startsWith(live + "/"))) return true;
  return false;
}

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
              <div
                lang="tr"
                className="mb-1 px-2 text-[10px] font-semibold tracking-wider text-muted-foreground"
              >
                {GROUP_LABEL_TR[group]}
              </div>
              <ul className="space-y-1">
                {items.map(({ href, label, icon: Icon }) => {
                  const active = isActive(href, pathname);
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
        <div className="font-mono text-foreground">v{process.env.NEXT_PUBLIC_ABS_VERSION ?? "1.0.6"}</div>
        <div>self-host AI orchestration</div>
      </div>
    </aside>
  );
}
