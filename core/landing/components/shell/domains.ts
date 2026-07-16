/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The shell's single source of truth: seven domains carrying every route the
// panel has. The rail draws one icon per domain, the context panel lists the
// active domain's pages, the mobile bar picks its four slots from the front of
// this array — none of them keeps its own copy.
//
// This replaced a 27-item flat sidebar. The finding that killed it was not
// "sidebars are dead" (Vercel returned to one in Feb 2026): a flat list makes
// the newcomer read everything before knowing where to start, and makes the
// operator scan everything to find the one thing that changed. Grouping fixes
// the first; the `status` field fixes the second — a domain that can demand
// attention names the signal here, and the rail renders it as a live dot.
// Navigation doubles as the monitoring surface.
import {
  BarChart3,
  Database,
  LayoutDashboard,
  Layers,
  MessageSquare,
  Settings,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface ShellPage {
  href: string;
  label: string;
}

export interface ShellDomain {
  id: string;
  label: string;
  icon: LucideIcon;
  pages: ShellPage[];
  /** Which live signal lights this domain's rail dot, if any. */
  status?: "approvals" | "providers" | "quota";
}

export const DOMAINS: ShellDomain[] = [
  {
    id: "overview",
    label: "Overview",
    icon: LayoutDashboard,
    pages: [{ href: "/admin/dashboard", label: "Overview" }],
  },
  {
    id: "assistant",
    label: "Assistant",
    icon: MessageSquare,
    pages: [
      { href: "/admin/chat", label: "Chat" },
      { href: "/admin/meetings", label: "Meetings" },
      { href: "/admin/transcription", label: "Live capture" },
    ],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    icon: Database,
    pages: [
      { href: "/admin/rag", label: "Company memory" },
      { href: "/admin/graph-context", label: "Customer map" },
      { href: "/admin/graph", label: "Graph console" },
    ],
  },
  {
    id: "growth",
    label: "Growth",
    icon: TrendingUp,
    status: "approvals",
    pages: [
      { href: "/admin/growth", label: "Copilot" },
      { href: "/admin/approvals", label: "Approvals" },
      { href: "/admin/leads", label: "Opportunities" },
      { href: "/admin/inbound", label: "Inbound replies" },
      { href: "/admin/agents", label: "Agents" },
      { href: "/admin/workflows", label: "Workflows" },
      { href: "/admin/connectors", label: "Data sources" },
    ],
  },
  {
    id: "engine",
    label: "Engine",
    icon: Layers,
    status: "providers",
    pages: [
      { href: "/admin/providers", label: "Providers" },
      { href: "/admin/provider-keys", label: "Provider keys" },
      { href: "/admin/pipelines", label: "Quality control" },
      { href: "/admin/mcp-tools", label: "Tool catalogue" },
      { href: "/admin/mcp-servers", label: "External tools" },
      { href: "/admin/mcp-tokens", label: "Access keys" },
      { href: "/admin/marketplace", label: "Add-ons" },
    ],
  },
  {
    id: "cost",
    label: "Cost",
    icon: BarChart3,
    status: "quota",
    pages: [
      { href: "/admin/usage", label: "Usage" },
      { href: "/admin/quota", label: "Limits" },
    ],
  },
  {
    id: "system",
    label: "System",
    icon: Settings,
    pages: [
      { href: "/admin/settings", label: "Settings" },
      { href: "/admin/users", label: "Users" },
      { href: "/admin/projects", label: "Projects" },
      { href: "/admin/audit", label: "Audit log" },
      { href: "/admin/system", label: "Delivery & errors" },
      { href: "/admin/account", label: "Account & privacy" },
    ],
  },
];

// A few pages still resolve to /panel/* via 308 redirects. Map both ways so the
// active highlight follows the user wherever the redirect lands them.
export const REDIRECT_EQUIVALENTS: Record<string, string> = {
  "/admin/chat": "/panel/chat",
  "/admin/meetings": "/panel/meetings",
  "/admin/transcription": "/panel/transcription",
  "/admin/mcp-tools": "/panel/tools",
  "/admin/quota": "/panel/quota",
  "/admin/dashboard": "/panel",
  "/admin/approvals": "/panel/approvals",
};

export function isActive(href: string, pathname: string): boolean {
  if (pathname === href) return true;
  if (pathname.startsWith(href + "/")) return true;
  const live = REDIRECT_EQUIVALENTS[href];
  if (!live) return false;
  if (pathname === live) return true;
  // "/panel" is the root of every page in the panel, so prefix-matching it made
  // Overview — which maps to it, and is first in DOMAINS — the active domain on
  // *every* route. The whole product read "Overview" in the rail and the
  // breadcrumb: on Chat, on Company memory, everywhere. Only the deeper
  // equivalences may prefix-match.
  if (live !== "/panel" && pathname.startsWith(live + "/")) return true;
  return false;
}

export function activeDomain(pathname: string): ShellDomain {
  return (
    DOMAINS.find((d) => d.pages.some((p) => isActive(p.href, pathname))) ??
    DOMAINS[0]
  );
}

export function activePage(pathname: string): ShellPage | undefined {
  for (const d of DOMAINS) {
    const page = d.pages.find((p) => isActive(p.href, pathname));
    if (page) return page;
  }
  return undefined;
}
