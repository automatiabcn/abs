/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Connector Marketplace. Stage A: a connector with a real
// adapter opens a credential form (file upload / api key), connects, and syncs
// real records into the growth tables (Lead Intelligence / Context Graph).
// GET /v1/connectors, GET /{id}/fields, POST /{id}/connect|sync|disconnect.
"use client";

import { useCallback, useEffect, useState } from "react";

type Field = { key: string; label: string; type: string; placeholder: string; required: boolean };
type Connector = {
  id: string; name: string; kind: string; note: string; local_priority: boolean;
  status: string; has_adapter: boolean; auth_kind: string;
  credential_fields: Field[]; last_sync_count: number; last_error: string | null;
};
type Group = { key: string; label: string; connectors: Connector[] };
type Data = { groups: Group[]; connected_total: number; catalog_total: number };

export default function ConnectorMarketplacePage() {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [modal, setModal] = useState<Connector | null>(null);
  // A connector with no working adapter used to "connect" on click — a flag flip
  // that moved no data and left the card reading "connected". This holds the
  // connector whose honest roadmap sheet is open instead.
  const [roadmap, setRoadmap] = useState<Connector | null>(null);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch("/v1/connectors", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Data) => setD(j)).catch((e) => setErr(String(e)));
  }, []);
  useEffect(load, [load]);

  // The one connector that actually authenticates and imports today: the
  // CSV/JSON file adapter. Every roadmap connector routes here.
  const csvImport = d?.groups
    .flatMap((g) => g.connectors)
    .find((c) => c.has_adapter && c.auth_kind === "file");

  function openCredentialModal(c: Connector) {
    setCreds(c.auth_kind === "file" ? { format: "csv" } : {});
    setResult(null);
    setModal(c);
  }
  function openConnect(c: Connector) {
    // A native adapter opens the real credential form; everything else is
    // honest about being on the roadmap rather than faking a connection.
    if (c.has_adapter) { openCredentialModal(c); return; }
    setRoadmap(c);
  }
  function importInstead() {
    const csv = csvImport;
    setRoadmap(null);
    if (csv) openCredentialModal(csv);
  }
  async function disconnect(c: Connector) {
    await fetch(`/v1/connectors/${c.id}/disconnect`, { method: "POST", credentials: "include" });
    load();
  }
  async function syncNow(c: Connector) {
    setBusy(true);
    try {
      const r = await fetch(`/v1/connectors/${c.id}/sync`, { method: "POST", credentials: "include" });
      const j = await r.json();
      setResult(j.ok ? `✓ ${j.total} records (${j.companies} companies · ${j.leads} leads)` : `Failed: ${j.error}`);
      load();
    } finally { setBusy(false); }
  }
  async function submitConnect() {
    if (!modal) return;
    setBusy(true); setResult(null);
    try {
      const r = await fetch(`/v1/connectors/${modal.id}/connect`, {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ credentials: creds }),
      });
      const j = await r.json();
      if (!j.ok) { setResult(`Failed: ${j.error ?? `HTTP ${r.status}`}`); return; }
      const s = j.sync;
      setResult(`✓ Connected · imported ${s?.total ?? 0} records (${s?.companies ?? 0} companies · ${s?.contacts ?? 0} contacts · ${s?.leads ?? 0} leads)`);
      load();
      setTimeout(() => setModal(null), 1400);
    } finally { setBusy(false); }
  }
  async function onFile(field: string, file: File | null) {
    if (!file) return;
    const text = await file.text();
    const fmt = file.name.endsWith(".json") ? "json" : "csv";
    setCreds((c) => ({ ...c, [field]: text, format: fmt }));
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Connector Marketplace</h1>
        <p className="mt-1 text-sm text-muted-foreground">Bring your data in. Read-only first, official APIs only.</p>
      </div>
      {err && <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Couldn&apos;t load the connectors: {err}</div>}
      {!d && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}
      {d && (
        <>
          <div className="mb-6 text-xs text-muted-foreground">{d.connected_total} connected of {d.catalog_total} available</div>
          {d.groups.map((g) => (
            <section key={g.key} className="mb-8">
              <h2 className="mb-3 text-base font-semibold">{g.label}</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {g.connectors.map((c) => (
                  <div key={c.id} className="flex items-start gap-3 rounded-lg border bg-card/60 p-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted/40 font-mono text-sm text-primary">{c.name[0]}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 text-sm font-semibold">
                        {c.name}
                        {c.local_priority && <span className="rounded-full border border-sky-500/40 px-1.5 text-[9px] text-sky-400">local</span>}
                        {c.has_adapter && <span className="rounded-full border border-emerald-500/40 px-1.5 text-[9px] text-emerald-700 dark:text-emerald-300">live</span>}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground">{c.kind} · {c.note}</div>
                      {c.status === "connected" && c.last_sync_count > 0 && (
                        <div className="mt-1 text-[10px] text-emerald-700 dark:text-emerald-300/80">{c.last_sync_count} records synced</div>
                      )}
                      {c.last_error && <div className="mt-1 text-[10px] text-rose-700 dark:text-rose-300/80">{c.last_error}</div>}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      {c.status === "connected" ? (
                        <>
                          {c.has_adapter && c.auth_kind !== "file" && (
                            <button onClick={() => syncNow(c)} disabled={busy} className="rounded-full border px-2.5 py-0.5 text-[10px] text-sky-700 dark:text-sky-300">Sync</button>
                          )}
                          <button onClick={() => disconnect(c)} className="rounded-full border border-emerald-500/40 px-2.5 py-0.5 text-[10px] text-emerald-400">Disconnect</button>
                        </>
                      ) : (
                        <button onClick={() => openConnect(c)} className="rounded-full border px-2.5 py-0.5 text-[10px] text-muted-foreground">Connect</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      )}

      {/* ── Roadmap sheet: honest path for connectors with no adapter ── */}
      {roadmap && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setRoadmap(null)}>
          <div className="w-full max-w-md rounded-xl border bg-card p-5" onClick={(e) => e.stopPropagation()} data-test="connector-roadmap">
            <div className="mb-1 text-base font-semibold">{roadmap.name} — coming soon</div>
            <p className="mb-3 text-[12px] leading-relaxed text-muted-foreground">
              A native {roadmap.name} sync isn&apos;t live yet, so this won&apos;t
              pull your data on its own. The fastest way to bring your {roadmap.name}{" "}
              data in today is to export it and import the CSV or JSON here — it
              lands in the same companies and leads tables a native sync would use.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setRoadmap(null)} className="rounded-md border px-3 py-1.5 text-xs">Close</button>
              {csvImport && (
                <button
                  onClick={importInstead}
                  className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground"
                  data-test="connector-roadmap-import"
                >
                  Import CSV / JSON
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Connect credential modal ──────────────── */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => !busy && setModal(null)}>
          <div className="w-full max-w-md rounded-xl border bg-card p-5" onClick={(e) => e.stopPropagation()}>
            <div className="mb-1 text-base font-semibold">Connect {modal.name}</div>
            <div className="mb-4 text-[11px] text-muted-foreground">
              {modal.auth_kind === "file" ? "Upload a CSV or JSON file (columns: company · sector · domain · email · score · intent)" : "Enter your credentials"}
            </div>
            <div className="space-y-3">
              {modal.credential_fields.map((f) => (
                <div key={f.key}>
                  <div className="mb-1 text-[11px] text-muted-foreground">{f.label}{f.required && " *"}</div>
                  {f.type === "file" ? (
                    <>
                      <input type="file" accept=".csv,.json,text/csv,application/json"
                        onChange={(e) => onFile(f.key, e.target.files?.[0] ?? null)}
                        className="w-full text-xs" data-test="connector-file" />
                      <textarea value={creds[f.key] ?? ""} onChange={(e) => setCreds((c) => ({ ...c, [f.key]: e.target.value }))}
                        rows={4} placeholder="…or paste the contents here" className="mt-2 w-full rounded-md border bg-background px-2 py-1 font-mono text-[11px]" />
                    </>
                  ) : f.key === "format" ? null : (
                    <input type={f.type === "password" ? "password" : "text"} value={creds[f.key] ?? ""}
                      onChange={(e) => setCreds((c) => ({ ...c, [f.key]: e.target.value }))}
                      placeholder={f.placeholder} className="w-full rounded-md border bg-background px-2 py-1.5 text-sm" />
                  )}
                </div>
              ))}
            </div>
            {result && <div className={`mt-3 rounded-md border px-3 py-2 text-xs ${result.startsWith("✓") ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200" : "border-rose-500/30 bg-rose-500/10 text-rose-200"}`}>{result}</div>}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setModal(null)} disabled={busy} className="rounded-md border px-3 py-1.5 text-xs">Cancel</button>
              <button onClick={submitConnect} disabled={busy} className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50" data-test="connector-connect-submit">{busy ? "Connecting…" : "Connect and import"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
