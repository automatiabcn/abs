/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q8 Phase M — global ⌘K command palette (cmdk powered).
// Surfaces every panel/admin route + key actions (run cascade, search
// tool, install plugin, switch session). Mounted once in the panel
// layouts so any page exposes the same shortcut.
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  BarChart3,
  Boxes,
  Brain,
  Database,
  Layers,
  LayoutDashboard,
  MessageSquare,
  Mic,
  Search,
  Settings,
  ShieldCheck,
  Sliders,
  Store,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";

interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  group: "Pages" | "Actions" | "Quick chat";
  icon: typeof LayoutDashboard;
  onSelect: () => void;
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    // The shell's search affordances (top strip button, mobile bar) open the
    // palette by event — a synthetic ⌘K keypress would be the hack version.
    function onOpenEvent() {
      setOpen(true);
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener("abs:palette", onOpenEvent);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("abs:palette", onOpenEvent);
    };
  }, []);

  // The palette reaches everything the nav does, under the same names — the ones
  // that say what a thing is for. Someone who searches "cascade" or "RAG" still
  // lands where they meant to: the old vocabulary is kept as a `hint`, which cmdk
  // matches on, so the rename costs no muscle memory.
  const items: PaletteItem[] = useMemo(
    () => [
      // Pages — mirrors PanelSidebar.
      { id: "go-overview", label: "Overview", group: "Pages", icon: LayoutDashboard, onSelect: () => { router.push("/admin/dashboard"); close(); } },
      { id: "go-chat", label: "Chat", group: "Pages", icon: MessageSquare, onSelect: () => { router.push("/admin/chat"); close(); } },
      { id: "go-rag", label: "Company memory", hint: "RAG · knowledge base", group: "Pages", icon: Database, onSelect: () => { router.push("/admin/rag"); close(); } },
      { id: "go-meetings", label: "Meetings", group: "Pages", icon: Mic, onSelect: () => { router.push("/admin/meetings"); close(); } },
      { id: "go-growth", label: "Growth copilot", group: "Pages", icon: LayoutDashboard, onSelect: () => { router.push("/admin/growth"); close(); } },
      { id: "go-usage", label: "Usage & cost", group: "Pages", icon: BarChart3, onSelect: () => { router.push("/admin/usage"); close(); } },
      { id: "go-settings", label: "Settings", group: "Pages", icon: Settings, onSelect: () => { router.push("/admin/settings"); close(); } },
      { id: "go-approvals", label: "Approvals", group: "Pages", icon: ShieldCheck, onSelect: () => { router.push("/admin/approvals"); close(); } },
      { id: "go-agents", label: "Agents", group: "Pages", icon: Brain, onSelect: () => { router.push("/admin/agents"); close(); } },
      { id: "go-workflows", label: "Workflows", group: "Pages", icon: Workflow, onSelect: () => { router.push("/admin/workflows"); close(); } },
      { id: "go-providers", label: "Providers", hint: "cascade · failover", group: "Pages", icon: Layers, onSelect: () => { router.push("/admin/providers"); close(); } },
      { id: "go-tools", label: "Tool catalogue", hint: "MCP tools", group: "Pages", icon: Wrench, onSelect: () => { router.push("/admin/mcp-tools"); close(); } },
      { id: "go-pipelines", label: "Quality control", hint: "pipelines", group: "Pages", icon: Sliders, onSelect: () => { router.push("/admin/pipelines"); close(); } },
      { id: "go-quota", label: "Limits", hint: "quota", group: "Pages", icon: BarChart3, onSelect: () => { router.push("/admin/quota"); close(); } },
      { id: "go-graph", label: "Graph console", hint: "knowledge graph · Cypher", group: "Pages", icon: Brain, onSelect: () => { router.push("/admin/graph"); close(); } },
      { id: "go-transcription", label: "Live capture", hint: "transcription", group: "Pages", icon: Boxes, onSelect: () => { router.push("/admin/transcription"); close(); } },
      { id: "go-marketplace", label: "Add-ons", hint: "marketplace", group: "Pages", icon: Store, onSelect: () => { router.push("/admin/marketplace"); close(); } },
      { id: "go-users", label: "Users", group: "Pages", icon: Users, onSelect: () => { router.push("/admin/users"); close(); } },
      { id: "go-audit", label: "Audit log", group: "Pages", icon: ShieldCheck, onSelect: () => { router.push("/admin/audit"); close(); } },
      // Actions
      { id: "act-new-chat", label: "Start a new chat", group: "Actions", icon: MessageSquare, onSelect: () => { router.push("/admin/chat"); close(); } },
      { id: "act-new-workflow", label: "Design a workflow", group: "Actions", icon: Workflow, onSelect: () => { router.push("/admin/workflows"); close(); } },
      { id: "act-test-cascade", label: "Test the provider chain", hint: "cascade", group: "Actions", icon: Layers, onSelect: () => { router.push("/admin/providers"); close(); } },
      { id: "act-invite-user", label: "Invite a teammate", group: "Actions", icon: Users, onSelect: () => { router.push("/admin/users"); close(); } },
      // Quick chat
      { id: "ask-rag", label: "Chat: /rag …", hint: "ask your knowledge base", group: "Quick chat", icon: Database, onSelect: () => { router.push("/admin/chat"); close(); } },
      { id: "ask-code", label: "Chat: /code …", hint: "generate code", group: "Quick chat", icon: Wrench, onSelect: () => { router.push("/admin/chat"); close(); } },
      { id: "ask-translate", label: "Chat: /translate …", hint: "translate text", group: "Quick chat", icon: MessageSquare, onSelect: () => { router.push("/admin/chat"); close(); } },
    ],
    [router, close],
  );

  if (!open) return null;

  return (
    <div
      data-test="command-palette"
      className="fixed inset-0 z-50 flex items-start justify-center bg-background/60 backdrop-blur-sm"
      onClick={close}
    >
      <div
        className="mt-24 w-full max-w-xl rounded-xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <Command label="ABS command palette" className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Command.Input
              value={search}
              onValueChange={setSearch}
              placeholder="Search pages, actions, commands…"
              data-test="command-palette-input"
              className="flex-1 bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground"
            />
            <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              ⌘K
            </kbd>
          </div>
          <Command.List className="max-h-96 overflow-y-auto p-2">
            <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">
              Nothing matches.
            </Command.Empty>
            {(["Pages", "Actions", "Quick chat"] as const).map((g) => {
              const groupItems = items.filter((it) => it.group === g);
              if (groupItems.length === 0) return null;
              return (
                <Command.Group key={g} heading={g} className="mb-2 [&_[cmdk-group-heading]]:mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                  {groupItems.map((it) => {
                    const Icon = it.icon;
                    return (
                      <Command.Item
                        key={it.id}
                        value={`${it.group} ${it.label} ${it.hint ?? ""}`}
                        onSelect={it.onSelect}
                        data-test="command-palette-item"
                        className="flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm aria-selected:bg-accent aria-selected:text-accent-foreground"
                      >
                        <span className="flex items-center gap-2">
                          <Icon className="h-4 w-4 text-muted-foreground" />
                          {it.label}
                        </span>
                        {it.hint && (
                          <span className="ml-2 text-[10px] text-muted-foreground">
                            {it.hint}
                          </span>
                        )}
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              );
            })}
          </Command.List>
          <div className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
            ↑↓ navigate · ↵ open · esc close
          </div>
        </Command>
      </div>
    </div>
  );
}
