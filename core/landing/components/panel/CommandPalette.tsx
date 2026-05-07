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
  group: "Sayfalar" | "Aksiyonlar" | "Hızlı sohbet";
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
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const items: PaletteItem[] = useMemo(
    () => [
      // Sayfalar (mirrors PanelSidebar)
      { id: "go-overview", label: "Genel Bakış", group: "Sayfalar", icon: LayoutDashboard, onSelect: () => { router.push("/panel"); close(); } },
      { id: "go-chat", label: "Sohbet", group: "Sayfalar", icon: MessageSquare, onSelect: () => { router.push("/panel/chat"); close(); } },
      { id: "go-workflow", label: "Workflow Builder", group: "Sayfalar", icon: Workflow, onSelect: () => { router.push("/admin/workflow-builder"); close(); } },
      { id: "go-tools", label: "MCP Tool Browser", group: "Sayfalar", icon: Wrench, onSelect: () => { router.push("/panel/tools"); close(); } },
      { id: "go-rag", label: "RAG / Bilgi Tabanı", group: "Sayfalar", icon: Database, onSelect: () => { router.push("/admin/rag"); close(); } },
      { id: "go-pipelines", label: "Quality Pipelines", group: "Sayfalar", icon: Sliders, onSelect: () => { router.push("/admin/pipelines"); close(); } },
      { id: "go-providers", label: "Provider Cascade", group: "Sayfalar", icon: Layers, onSelect: () => { router.push("/admin/providers"); close(); } },
      { id: "go-marketplace", label: "Marketplace", group: "Sayfalar", icon: Store, onSelect: () => { router.push("/admin/marketplace"); close(); } },
      { id: "go-quota", label: "Kota", group: "Sayfalar", icon: BarChart3, onSelect: () => { router.push("/panel/quota"); close(); } },
      { id: "go-graph", label: "Knowledge Graph", group: "Sayfalar", icon: Brain, onSelect: () => { router.push("/admin/graph"); close(); } },
      { id: "go-meetings", label: "Toplantılar", group: "Sayfalar", icon: Mic, onSelect: () => { router.push("/panel/meetings"); close(); } },
      { id: "go-transcription", label: "Transcription", group: "Sayfalar", icon: Boxes, onSelect: () => { router.push("/panel/transcription"); close(); } },
      { id: "go-settings", label: "Ayarlar", group: "Sayfalar", icon: Settings, onSelect: () => { router.push("/admin/settings"); close(); } },
      { id: "go-users", label: "Kullanıcılar", group: "Sayfalar", icon: Users, onSelect: () => { router.push("/admin/users"); close(); } },
      { id: "go-audit", label: "Denetim", group: "Sayfalar", icon: ShieldCheck, onSelect: () => { router.push("/admin/audit"); close(); } },
      // Aksiyonlar
      { id: "act-new-chat", label: "Yeni sohbet başlat", hint: "/panel/chat?new=1", group: "Aksiyonlar", icon: MessageSquare, onSelect: () => { router.push("/panel/chat"); close(); } },
      { id: "act-new-workflow", label: "Yeni iş akışı tasarla", group: "Aksiyonlar", icon: Workflow, onSelect: () => { router.push("/admin/workflow-builder"); close(); } },
      { id: "act-test-cascade", label: "Cascade test çağrısı", group: "Aksiyonlar", icon: Layers, onSelect: () => { router.push("/admin/providers"); close(); } },
      { id: "act-invite-user", label: "Kullanıcı davet et", group: "Aksiyonlar", icon: Users, onSelect: () => { router.push("/admin/users"); close(); } },
      // Hızlı sohbet
      { id: "ask-rag", label: "Sohbet: /rag …", hint: "RAG bilgi tabanı sorgusu", group: "Hızlı sohbet", icon: Database, onSelect: () => { router.push("/panel/chat"); close(); } },
      { id: "ask-code", label: "Sohbet: /code …", hint: "Kod üret (qual_code)", group: "Hızlı sohbet", icon: Wrench, onSelect: () => { router.push("/panel/chat"); close(); } },
      { id: "ask-translate", label: "Sohbet: /translate …", hint: "Çeviri (qual_translate)", group: "Hızlı sohbet", icon: MessageSquare, onSelect: () => { router.push("/panel/chat"); close(); } },
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
        <Command label="ABS komut paleti" className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Command.Input
              value={search}
              onValueChange={setSearch}
              placeholder="Sayfa, aksiyon veya komut ara…"
              data-test="command-palette-input"
              className="flex-1 bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground"
            />
            <kbd className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              ⌘K
            </kbd>
          </div>
          <Command.List className="max-h-96 overflow-y-auto p-2">
            <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">
              Eşleşen aksiyon yok.
            </Command.Empty>
            {(["Sayfalar", "Aksiyonlar", "Hızlı sohbet"] as const).map((g) => {
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
            ↑↓ gez · Enter aç · Esc kapat · ⌘K toggle
          </div>
        </Command>
      </div>
    </div>
  );
}
