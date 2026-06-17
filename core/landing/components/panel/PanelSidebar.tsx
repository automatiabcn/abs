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

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Boxes,
  Brain,
  Database,
  FolderKanban,
  LayoutDashboard,
  Layers,
  Menu,
  MessageSquare,
  Mic,
  Server,
  Settings,
  KeyRound,
  ShieldCheck,
  Sliders,
  Store,
  Users,
  Workflow,
  Wrench,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavGroup = "Agentic Growth" | "Üretim" | "Operasyon" | "Toplantılar" | "Yönetim";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  group: NavGroup;
}

const NAV: NavItem[] = [
  // ── Agentic Growth (yeni ürün ekranları) ───────
  // Canonical /admin/* routes (re-export the /panel/* client components);
  // Caddy 308s /panel → /admin, so /admin/* is the surface the sidebar links.
  { href: "/admin/growth", label: "Growth Dashboard", icon: LayoutDashboard, group: "Agentic Growth" },
  { href: "/admin/agents", label: "Agent Registry", icon: Brain, group: "Agentic Growth" },
  { href: "/admin/workflows", label: "Workflow Designer", icon: Workflow, group: "Agentic Growth" },
  { href: "/admin/approvals", label: "Approval Center", icon: ShieldCheck, group: "Agentic Growth" },
  { href: "/admin/leads", label: "Lead Intelligence", icon: BarChart3, group: "Agentic Growth" },
  { href: "/admin/graph-context", label: "Context Graph", icon: Boxes, group: "Agentic Growth" },
  { href: "/admin/inbound", label: "Inbound + Knowledge", icon: MessageSquare, group: "Agentic Growth" },
  { href: "/admin/connectors", label: "Connectors", icon: Store, group: "Agentic Growth" },
  // ── Üretim ─────────────────────────────────────
  // Sprint 2B BUG-19 — Genel Bakış now lands on the new /admin/dashboard
  // route (5-source aggregated overview) instead of /panel home.
  { href: "/admin/dashboard", label: "Genel Bakış", icon: LayoutDashboard, group: "Üretim" },
  // Sprint 2B BUG-20 — /admin/chat is now a real page (not a 308 to
  // /panel/chat). Same for /admin/mcp-tools and /admin/quota below.
  { href: "/admin/chat", label: "Sohbet", icon: MessageSquare, group: "Üretim" },
  // Workflow lives in ONE place — the visual "Workflow Designer" under Agentic
  // Growth. The old /admin/workflow-builder (natural-language synth) used a
  // different node model and a duplicate "Workflow" entry here; it now redirects
  // to the Designer so there is a single, coherent Workflow experience.
  // BUG-V1 — /admin/usage Free path % + Claude budget % widget.
  { href: "/admin/usage", label: "Kullanım", icon: BarChart3, group: "Üretim" },
  { href: "/admin/mcp-tools", label: "MCP Tools", icon: Wrench, group: "Üretim" },
  // External MCP federation — ABS as MCP client (register 3rd-party servers).
  { href: "/admin/mcp-servers", label: "Harici MCP", icon: Server, group: "Üretim" },
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
  { href: "/admin/projects", label: "Projeler", icon: FolderKanban, group: "Yönetim" },
  { href: "/admin/users", label: "Kullanıcılar", icon: Users, group: "Yönetim" },
  { href: "/admin/mcp-tokens", label: "MCP Token", icon: KeyRound, group: "Yönetim" },
  { href: "/admin/audit", label: "Denetim", icon: ShieldCheck, group: "Yönetim" },
];

const GROUP_ORDER: NavGroup[] = ["Agentic Growth", "Üretim", "Operasyon", "Toplantılar", "Yönetim"];

// Polish round R4 — CSS `text-transform: uppercase` runs in the document
// locale (English by default) and turns Turkish "i" into dotless "I"
// instead of "İ". Pre-render the labels with `toLocaleUpperCase("tr-TR")`
// and drop the CSS transform so the dotted İ comes through verbatim.
const GROUP_LABEL_TR: Record<NavGroup, string> = {
  "Agentic Growth": "Agentic Growth".toLocaleUpperCase("tr-TR"),
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

function NavBody({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <>
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
      <nav aria-label="Panel menüsü" className="space-y-4">
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
                        onClick={onNavigate}
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
    </>
  );
}

export function PanelSidebar() {
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);

  // Close the mobile drawer on every route change (i.e. after a nav click).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Desktop static rail (≥ lg). */}
      <aside
        data-test="panel-sidebar"
        className="hidden w-60 shrink-0 border-r border-border bg-card/50 p-4 lg:flex lg:flex-col"
      >
        <NavBody pathname={pathname} />
      </aside>

      {/* Mobile: floating nav button (bottom-right FAB avoids the header's
          left breadcrumb + right action icons → no overlap). */}
      <button
        type="button"
        aria-label="Menü"
        data-test="panel-nav-toggle"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 rounded-full border border-border bg-card p-3 text-foreground shadow-lg lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Mobile slide-out drawer + backdrop. */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <aside
            data-test="panel-sidebar-mobile"
            className="absolute left-0 top-0 flex h-full w-64 flex-col overflow-y-auto border-r border-border bg-card p-4 shadow-xl"
          >
            <button
              type="button"
              aria-label="Menüyü kapat"
              onClick={() => setOpen(false)}
              className="mb-2 self-end rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
            <NavBody pathname={pathname} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
