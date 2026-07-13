/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The panel's navigation.
//
// It used to list twenty-seven items across five groups, flat and all at once,
// in two languages at the same time ("Growth Dashboard" sat directly above
// "Sohbet"). Someone seeing the product for the first time had to read the
// whole rail before knowing where to start, and half of it named machinery
// ("Cascade", "Quality Pipelines", "MCP Token") rather than anything they came
// to do.
//
// Now seven items carry the jobs people actually arrive with, and the other
// twenty sit under Advanced — collapsed, one click away, nothing removed. The
// route table is unchanged; only what greets you is.
//
// Labels are English: the product ships globally (see CLAUDE.md) and the panel
// is next in line for i18n. One language at a time, not two.
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Boxes,
  Brain,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Database,
  FolderKanban,
  Gauge,
  KeyRound,
  LayoutDashboard,
  Layers,
  Menu,
  MessageSquare,
  Mic,
  Plug,
  Server,
  Settings,
  ShieldCheck,
  Sliders,
  Store,
  TrendingUp,
  Users,
  Workflow,
  Wrench,
  X,
} from "lucide-react";

import AbsLogo from "@/components/icons/AbsLogo";
import { cn } from "@/lib/utils";

const COLLAPSE_KEY = "abs.sidebar.collapsed";
const ADVANCED_KEY = "abs.sidebar.advanced";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
}

// What someone opens the panel to do.
const PRIMARY: NavItem[] = [
  { href: "/admin/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/chat", label: "Chat", icon: MessageSquare },
  { href: "/admin/rag", label: "Company memory", icon: Database },
  { href: "/admin/meetings", label: "Meetings", icon: Mic },
  { href: "/admin/growth", label: "Growth copilot", icon: TrendingUp },
  { href: "/admin/usage", label: "Usage & cost", icon: BarChart3 },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

// Everything the product can do, one click down. Names say what the thing is
// for; the machinery keeps its old route.
const ADVANCED: NavItem[] = [
  { href: "/admin/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/admin/agents", label: "Agents", icon: Brain },
  { href: "/admin/workflows", label: "Workflows", icon: Workflow },
  { href: "/admin/leads", label: "Opportunities", icon: TrendingUp },
  { href: "/admin/graph-context", label: "Customer map", icon: Boxes },
  { href: "/admin/inbound", label: "Inbound replies", icon: MessageSquare },
  { href: "/admin/connectors", label: "Data sources", icon: Plug },
  { href: "/admin/transcription", label: "Live capture", icon: Mic },
  { href: "/admin/mcp-tools", label: "Tool catalogue", icon: Wrench },
  { href: "/admin/mcp-servers", label: "External tools", icon: Server },
  { href: "/admin/mcp-tokens", label: "Access keys", icon: KeyRound },
  { href: "/admin/pipelines", label: "Quality control", icon: Sliders },
  { href: "/admin/providers", label: "Providers", icon: Layers },
  { href: "/admin/provider-keys", label: "Provider keys", icon: KeyRound },
  { href: "/admin/quota", label: "Limits", icon: Gauge },
  { href: "/admin/graph", label: "Graph console", icon: Brain },
  { href: "/admin/marketplace", label: "Add-ons", icon: Store },
  { href: "/admin/projects", label: "Projects", icon: FolderKanban },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/audit", label: "Audit log", icon: ShieldCheck },
];

// A few pages still resolve to /panel/* via 308 redirects. Map both ways so the
// active highlight follows the user wherever the redirect lands them.
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

function NavLink({
  item,
  pathname,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const active = isActive(item.href, pathname);
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        data-active={active}
        onClick={onNavigate}
        title={collapsed ? item.label : undefined}
        className={cn(
          "relative flex items-center rounded text-sm transition-colors",
          collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3 py-2",
          active
            ? "bg-primary-soft font-medium text-primary"
            : "text-muted-foreground hover:bg-surface-raised hover:text-foreground",
        )}
      >
        {active && !collapsed && (
          <span
            aria-hidden="true"
            className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded bg-primary"
          />
        )}
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </Link>
    </li>
  );
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
  // Advanced opens itself when you are standing inside it, so a deep link never
  // lands you on a page your own nav appears not to contain.
  const inAdvanced = ADVANCED.some((item) => isActive(item.href, pathname));
  const [advancedOpen, setAdvancedOpen] = useState(inAdvanced);

  useEffect(() => {
    if (inAdvanced) {
      setAdvancedOpen(true);
      return;
    }
    try {
      if (localStorage.getItem(ADVANCED_KEY) === "1") setAdvancedOpen(true);
    } catch {
      /* localStorage unavailable — default collapsed */
    }
  }, [inAdvanced]);

  function toggleAdvanced() {
    setAdvancedOpen((open) => {
      const next = !open;
      try {
        localStorage.setItem(ADVANCED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  return (
    <>
      <div
        className={cn(
          "mb-6 flex items-center gap-2.5",
          collapsed ? "flex-col" : "px-1",
        )}
      >
        <AbsLogo size={28} className="shrink-0 text-foreground" />
        {!collapsed && (
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="text-sm font-semibold tracking-tight text-foreground">
              Automatia ABS
            </span>
            <span className="text-[11px] text-subtle">Your AI, your server</span>
          </div>
        )}
        {onToggleCollapse && (
          <button
            type="button"
            data-test="panel-collapse-toggle"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand menu" : "Collapse menu"}
            title={collapsed ? "Expand" : "Collapse"}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" />
            ) : (
              <ChevronsLeft className="h-4 w-4" />
            )}
          </button>
        )}
      </div>

      <nav aria-label="Panel menu" className="space-y-4">
        <ul className="space-y-1">
          {PRIMARY.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              pathname={pathname}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          ))}
        </ul>

        <div>
          {!collapsed && (
            <button
              type="button"
              data-test="panel-advanced-toggle"
              onClick={toggleAdvanced}
              aria-expanded={advancedOpen}
              className="mb-1 flex w-full items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-subtle transition-colors hover:text-foreground"
            >
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  advancedOpen ? "rotate-0" : "-rotate-90",
                )}
              />
              Advanced
            </button>
          )}
          {(advancedOpen || collapsed) && (
            <ul className="space-y-1">
              {ADVANCED.map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  pathname={pathname}
                  collapsed={collapsed}
                  onNavigate={onNavigate}
                />
              ))}
            </ul>
          )}
        </div>
      </nav>

      {!collapsed && (
        <div className="mt-auto rounded border border-border-soft bg-surface-raised p-3 text-[11px] text-muted-foreground">
          <div className="num-mono text-foreground">
            v{process.env.NEXT_PUBLIC_ABS_VERSION ?? "1.0.6"}
          </div>
          <div>Self-hosted · your data stays here</div>
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
          "hidden shrink-0 overflow-y-auto border-r border-border bg-surface transition-[width] duration-200 ease-out lg:flex lg:flex-col",
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
        aria-label="Menu"
        data-test="panel-nav-toggle"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 rounded-full border border-border bg-surface p-3 text-foreground shadow-lg lg:hidden"
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
            className="absolute left-0 top-0 flex h-full w-64 flex-col overflow-y-auto border-r border-border bg-surface p-4 shadow-lg"
          >
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="mb-2 self-end rounded p-1.5 text-muted-foreground hover:bg-surface-raised hover:text-foreground"
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
