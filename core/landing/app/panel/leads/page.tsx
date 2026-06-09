/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Lead Intelligence. Faithful to mockup 07: a selected lead's
// 15-criterion score breakdown (bars), top-3 evidence, buying group and
// recommended action, plus the account-priority table. GET /v1/leads,
// GET /v1/leads/{id}, POST /{id}/score, POST create.
"use client";

import { useCallback, useEffect, useState } from "react";

type Lead = {
  id: number; company_name: string; sector: string; intent: string; score: number;
  status: string; consent_status: string; recommended_action: string;
  source: string; buying_group_count: number;
};
type Evidence = { kind: string; ref: string };
type Member = { name: string; role: string; consent_status: string };
type Detail = Lead & {
  score_breakdown: Record<string, number>;
  evidence: Evidence[];
  buying_group: Member[];
};

const INTENT: Record<string, string> = {
  high: "border-rose-500/40 text-rose-300", medium: "border-amber-500/40 text-amber-300",
  watching: "border-sky-500/40 text-sky-300",
};
const EV_LABEL: Record<string, string> = { rag: "RAG", graph: "GRAPH", signal: "SIGNAL" };
const ROLE_LABEL: Record<string, string> = {
  decision_maker: "Decision maker", finance_approver: "Finance approver",
  technical_evaluator: "Technical evaluator", gatekeeper: "Gatekeeper", purchasing: "Purchasing",
};

export default function LeadIntelligencePage() {
  const [items, setItems] = useState<Lead[] | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");

  const load = useCallback(() => {
    fetch("/v1/leads", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: { items: Lead[] }) => {
        setItems(j.items);
        if (j.items.length && !detail) void select(j.items[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, [detail]);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function select(id: number) {
    const r = await fetch(`/v1/leads/${id}`, { credentials: "include", cache: "no-store" });
    if (r.ok) setDetail(await r.json());
  }
  async function create() {
    if (!name.trim()) return;
    await fetch("/v1/leads", {
      method: "POST", credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ company_name: name, source: "manual" }),
    });
    setName(""); load();
  }
  async function score(id: number) {
    await fetch(`/v1/leads/${id}/score`, { method: "POST", credentials: "include" });
    load(); void select(id);
  }

  const crits = detail ? Object.entries(detail.score_breakdown).filter(([, v]) => typeof v === "number") : [];

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Lead Intelligence</h1>
          <p className="mt-1 text-[12px] text-muted-foreground">Account priority · Lead Scoring Agent (15 kriter + top-3 kanıt + buying group)</p>
        </div>
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Yeni firma adı…"
            className="rounded-md border bg-background px-3 py-2 text-sm" />
          <button onClick={create} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">+ Lead</button>
        </div>
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Yüklenemedi: {err}</div>}
      {!items && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {/* ── Lead detail ─────────────────────────── */}
      {detail && crits.length > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">⚖ Skor Kırılımı <span className="font-normal text-muted-foreground">· {detail.company_name} · Lead Scoring Agent</span></div>
            <div className="space-y-2">
              {crits.map(([k, v]) => (
                <div key={k} className="flex items-center gap-3 text-[12px]">
                  <span className="w-44 shrink-0 text-muted-foreground">{k}</span>
                  <div className="h-[6px] flex-1 overflow-hidden rounded bg-muted/40">
                    <div className="h-full rounded" style={{ width: `${Math.round(v * 100)}%`, background: "linear-gradient(90deg,#1e57ac,#3a9dff)" }} />
                  </div>
                  <span className="w-9 shrink-0 text-right font-mono">{v.toFixed(2).replace(/^0/, "")}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-xl border border-teal-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">◈ Kanıtlar (top-3)</div>
              <div className="space-y-1.5 text-[12px]">
                {detail.evidence.slice(0, 3).map((e, i) => (
                  <div key={i} className="flex gap-2"><span className="font-mono text-[10px] text-teal-300">{EV_LABEL[e.kind] ?? e.kind}</span><span className="text-muted-foreground">{e.ref}</span></div>
                ))}
                {detail.evidence.length === 0 && <div className="text-muted-foreground">Kanıt yok — Skorla.</div>}
              </div>
            </div>
            <div className="rounded-xl border border-purple-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">👥 Buying Group</div>
              <div className="space-y-1 text-[12px]">
                {detail.buying_group.map((m, i) => (
                  <div key={i} className="flex justify-between"><span className="text-muted-foreground">{ROLE_LABEL[m.role] ?? m.role}</span><span>{m.name}</span></div>
                ))}
                {detail.buying_group.length === 0 && <div className="text-muted-foreground">—</div>}
              </div>
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">→ Önerilen Aksiyon</div>
              <p className="text-[12px] text-muted-foreground">{detail.recommended_action} · consent {detail.consent_status || "—"}.</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Account priority table ──────────────── */}
      {items && (
        <div className="rounded-xl border bg-card/60 p-4">
          <div className="mb-3 text-sm font-semibold">◷ Account Priority Listesi <span className="font-normal text-muted-foreground">· tüm leadler</span></div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="pb-2 pr-3 font-medium">Firma</th><th className="pb-2 pr-3 font-medium">Sektör</th>
                <th className="pb-2 pr-3 font-medium">Skor</th><th className="pb-2 pr-3 font-medium">Intent</th>
                <th className="pb-2 pr-3 font-medium">Consent</th><th className="pb-2 pr-3 font-medium">Buying group</th>
                <th className="pb-2 pr-3 font-medium">Kaynak</th><th className="pb-2 pr-3 font-medium">Sonraki adım</th><th className="pb-2 font-medium"></th>
              </tr></thead>
              <tbody className="divide-y divide-border">
                {items.length === 0 && <tr><td colSpan={9} className="py-4 text-muted-foreground">Henüz lead yok.</td></tr>}
                {items.map((l) => (
                  <tr key={l.id} onClick={() => select(l.id)} className={`cursor-pointer ${detail?.id === l.id ? "bg-primary/5" : ""}`}>
                    <td className="py-2.5 pr-3 font-medium">{l.company_name}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.sector || "—"}</td>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-2">
                        <div className="h-[5px] w-14 overflow-hidden rounded bg-muted/40"><div className="h-full" style={{ width: `${Math.round(l.score * 100)}%`, background: "linear-gradient(90deg,#1e57ac,#3a9dff)" }} /></div>
                        <span className="font-mono text-xs">{l.score.toFixed(2)}</span>
                      </div>
                    </td>
                    <td className="py-2.5 pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] ${INTENT[l.intent] ?? ""}`}>{l.intent}</span></td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.consent_status || "—"}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.buying_group_count} rol</td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-muted-foreground">{l.source || "—"}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.recommended_action}</td>
                    <td className="py-2.5"><button onClick={(e) => { e.stopPropagation(); score(l.id); }} className="rounded-md border px-2.5 py-1 text-[11px]">Skorla</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
