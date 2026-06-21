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
  ChevronsLeft,
  ChevronsRight,
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

// Desktop rail collapse state persists across sessions/routes.
const COLLAPSE_KEY = "abs.sidebar.collapsed";

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
  { href: "/admin/provider-keys", label: "Sağlayıcı Anahtarları", icon: KeyRound, group: "Operasyon" },
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
  collapsed = false,
  onToggleCollapse,
}: {
  pathname: string;
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  return (
    <>
      <div
        className={cn(
          "mb-6 flex items-center gap-2",
          collapsed ? "flex-col" : "px-1",
        )}
      >
        <img
          src="/abs-logo.png"
          alt="ABS"
          width={36}
          height={36}
          className="h-9 w-9 shrink-0 rounded-lg ring-1 ring-primary/30 shadow-[0_4px_16px_rgba(129,140,248,0.28)]"
        />
        {!collapsed && (
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="bg-gradient-to-r from-foreground to-primary bg-clip-text font-mono text-base font-bold tracking-[0.2em] text-transparent">
              ABS
            </span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Operator
            </span>
          </div>
        )}
        {onToggleCollapse && (
          <button
            type="button"
            data-test="panel-collapse-toggle"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Menüyü genişlet" : "Menüyü daralt"}
            title={collapsed ? "Genişlet" : "Daralt"}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" />
            ) : (
              <ChevronsLeft className="h-4 w-4" />
            )}
          </button>
        )}
      </div>
      <nav aria-label="Panel menüsü" className={cn(collapsed ? "space-y-2" : "space-y-4")}>
        {GROUP_ORDER.map((group) => {
          const items = NAV.filter((n) => n.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group}>
              {!collapsed && (
                <div
                  lang="tr"
                  className="mb-1 px-2 text-[10px] font-semibold tracking-wider text-muted-foreground"
                >
                  {GROUP_LABEL_TR[group]}
                </div>
              )}
              <ul className="space-y-1">
                {items.map(({ href, label, icon: Icon }) => {
                  const active = isActive(href, pathname);
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        data-active={active}
                        onClick={onNavigate}
                        title={collapsed ? label : undefined}
                        className={cn(
                          "relative flex items-center rounded-md text-sm transition-colors",
                          collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3 py-2",
                          active
                            ? "bg-gradient-to-r from-primary/15 to-primary/5 text-primary"
                            : "text-muted-foreground hover:bg-accent hover:text-foreground",
                        )}
                      >
                        {active && !collapsed && (
                          <span
                            aria-hidden="true"
                            className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                          />
                        )}
                        <Icon className="h-4 w-4 shrink-0" />
                        {!collapsed && <span className="truncate">{label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
      {!collapsed && (
        <div className="mt-auto rounded-md border border-border bg-background/40 p-3 text-[11px] text-muted-foreground">
          <div className="font-mono text-foreground">v{process.env.NEXT_PUBLIC_ABS_VERSION ?? "1.0.6"}</div>
          <div>self-host AI orchestration</div>
        </div>
      )}
    </>
  );
}

export function PanelSidebar() {
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // Close the mobile drawer on every route change (i.e. after a nav click).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Restore the persisted desktop collapse preference (client-only).
  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true);
    } catch {
      /* localStorage unavailable — default expanded */
    }
  }, []);

  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  return (
    <>
      {/* Desktop rail (≥ lg) — collapsible to an icon-only strip. */}
      <aside
        data-test="panel-sidebar"
        data-collapsed={collapsed}
        className={cn(
          "hidden shrink-0 border-r border-border bg-card/50 transition-[width] duration-200 ease-out lg:flex lg:flex-col",
          collapsed ? "w-[68px] px-2 py-4" : "w-60 p-4",
        )}
      >
        <NavBody
          pathname={pathname}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapsed}
        />
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
