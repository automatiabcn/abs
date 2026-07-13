/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The panel shell: live strip on top, icon rail + context panel on the left,
// floating bar on phones. Replaces the former PanelSidebar + PanelHeader pair.
//
// Three layers, three jobs: the rail says which domain, the context panel says
// which page, ⌘K goes anywhere without either. The context panel collapses to
// nothing (⌥\ or the strip button) for operators who live in one screen —
// zero-chrome is a mode the user chooses, never something the shell decides
// for them.
"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { ContextPanel } from "@/components/shell/ContextPanel";
import { MobileBar } from "@/components/shell/MobileBar";
import { Rail } from "@/components/shell/Rail";
import { TopStrip } from "@/components/shell/TopStrip";
import { useShellStatus } from "@/components/shell/useShellStatus";

const CHROME_KEY = "abs.shell.chrome";

export function AppShell({ children }: { children: ReactNode }) {
  const status = useShellStatus();
  const [chrome, setChrome] = useState(true);

  useEffect(() => {
    try {
      if (localStorage.getItem(CHROME_KEY) === "0") setChrome(false);
    } catch {
      /* localStorage unavailable — default expanded */
    }
  }, []);

  const toggleChrome = useCallback(() => {
    setChrome((current) => {
      const next = !current;
      try {
        localStorage.setItem(CHROME_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.altKey && (e.key === "\\" || e.code === "Backslash")) {
        e.preventDefault();
        toggleChrome();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggleChrome]);

  return (
    <div data-test="app-shell" className="flex min-h-screen flex-col bg-background text-foreground">
      <TopStrip status={status} chrome={chrome} onToggleChrome={toggleChrome} />
      <div className="flex min-h-0 flex-1">
        <Rail status={status} />
        {chrome && <ContextPanel status={status} />}
        {/* pb clears the floating mobile bar; desktop needs none. */}
        <main className="min-w-0 flex-1 overflow-x-hidden pb-24 lg:pb-0">{children}</main>
      </div>
      <MobileBar status={status} />
    </div>
  );
}
