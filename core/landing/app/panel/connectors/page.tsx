/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Connector Marketplace. GET /v1/connectors + connect/disconnect.
"use client";

import { useCallback, useEffect, useState } from "react";

type Connector = {
  id: string; name: string; kind: string; note: string;
  local_priority: boolean; status: string;
};
type Group = { key: string; label: string; connectors: Connector[] };
type Data = { groups: Group[]; connected_total: number; catalog_total: number };

export default function ConnectorMarketplacePage() {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch("/v1/connectors", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Data) => setD(j))
      .catch((e) => setErr(String(e)));
  }, []);
  useEffect(load, [load]);

  async function toggle(c: Connector) {
    const action = c.status === "connected" ? "disconnect" : "connect";
    await fetch(`/v1/connectors/${c.id}/${action}`, { method: "POST", credentials: "include" });
    load();
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Connector Marketplace</h1>
        <p className="mt-1 text-sm text-muted-foreground">MCP-tabanlı · read-first · resmi API / onaylı kanal · yerel-ERP önceliği</p>
      </div>
      {err && <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Yüklenemedi: {err}</div>}
      {!d && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}
      {d && (
        <>
          <div className="mb-6 text-xs text-muted-foreground">{d.connected_total} bağlı / {d.catalog_total} katalog</div>
          {d.groups.map((g) => (
            <section key={g.key} className="mb-8">
              <h2 className="mb-3 text-base font-semibold">{g.label}</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {g.connectors.map((c) => (
                  <div key={c.id} className="flex items-center gap-3 rounded-lg border bg-card/60 p-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted/40 font-mono text-sm text-primary">{c.name[0]}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-sm font-semibold">
                        {c.name}
                        {c.local_priority && <span className="rounded-full border border-sky-500/40 px-1.5 text-[9px] text-sky-400">yerel</span>}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground">{c.kind} · {c.note}</div>
                    </div>
                    <button onClick={() => toggle(c)}
                      className={`ml-auto rounded-full border px-2.5 py-0.5 text-[10px] ${c.status === "connected" ? "border-emerald-500/40 text-emerald-400" : "text-muted-foreground"}`}>
                      {c.status === "connected" ? "bağlı" : "bağla"}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
