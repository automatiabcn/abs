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
  high: "border-rose-500/40 text-rose-700 dark:text-rose-300", medium: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  watching: "border-sky-500/40 text-sky-700 dark:text-sky-300",
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
  // Manual lead entry — a discoverable form (not just a single field).
  const [showForm, setShowForm] = useState(false);
  const [sector, setSector] = useState("");
  const [domain, setDomain] = useState("");
  const [location, setLocation] = useState("");
  const [size, setSize] = useState("");
  const [consent, setConsent] = useState("");
  const [creating, setCreating] = useState(false);

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
    try {
      const r = await fetch(`/v1/leads/${id}`, { credentials: "include", cache: "no-store" });
      if (!r.ok) { setErr(`Could not open this lead (HTTP ${r.status})`); return; }
      setDetail(await r.json());
      setErr(null);
    } catch {
      setErr("Could not open this lead. Check your connection and try again.");
    }
  }
  async function create() {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const r = await fetch("/v1/leads", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          company_name: name.trim(), sector, domain, location, size,
          consent_status: consent, source: "manual",
        }),
      });
      // Only clear the form + refresh when the backend actually accepted it —
      // otherwise the user sees a "saved" UI for a lead that was never created.
      if (!r.ok) { setErr(`Could not create the lead (HTTP ${r.status})`); return; }
      setName(""); setSector(""); setDomain(""); setLocation(""); setSize(""); setConsent("");
      setShowForm(false);
      setErr(null);
      load();
    } catch {
      setErr("Could not create the lead. Check your connection and try again.");
    } finally {
      setCreating(false);
    }
  }
  async function score(id: number) {
    try {
      const r = await fetch(`/v1/leads/${id}/score`, { method: "POST", credentials: "include" });
      if (!r.ok) { setErr(`Scoring failed (HTTP ${r.status})`); return; }
      setErr(null);
      load(); void select(id);
    } catch {
      setErr("Scoring failed. Check your connection and try again.");
    }
  }

  const crits = detail ? Object.entries(detail.score_breakdown).filter(([, v]) => typeof v === "number") : [];

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Opportunities</h1>
          <p className="mt-1 text-[12px] text-muted-foreground">Every lead scored on 15 criteria, with the evidence behind the score and who to talk to.</p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          data-test="lead-add-toggle"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          {showForm ? "× Close" : "+ Add lead"}
        </button>
      </div>

      {/* ── Manual lead entry form ───────────────── */}
      {showForm && (
        <div className="mb-6 rounded-xl border bg-card/60 p-4" data-test="lead-add-form">
          <div className="mb-3 text-sm font-semibold">Add a lead</div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Company name *</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Northwind Logistics Ltd"
                data-test="lead-field-name"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Industry</span>
              <input value={sector} onChange={(e) => setSector(e.target.value)} placeholder="Construction, SaaS…"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Website</span>
              <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="example.com"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Location</span>
              <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="London"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Company size</span>
              <select value={size} onChange={(e) => setSize(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm">
                <option value="">—</option>
                <option value="1-10">1-10</option>
                <option value="11-50">11-50</option>
                <option value="51-200">51-200</option>
                <option value="200+">200+</option>
              </select>
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Marketing consent</span>
              <select value={consent} onChange={(e) => setConsent(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm">
                <option value="">—</option>
                <option value="opted_in">opted_in</option>
                <option value="pending">pending</option>
                <option value="opted_out">opted_out</option>
              </select>
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={create} disabled={!name.trim() || creating}
              data-test="lead-create-submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              {creating ? "Adding…" : "Add lead"}
            </button>
            <span className="text-[11px] text-muted-foreground">
              Once it&apos;s added, hit &quot;Score&quot; to rank it against your other leads.
            </span>
          </div>
        </div>
      )}
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">{err}</div>}
      {!items && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {/* ── Lead detail ─────────────────────────── */}
      {detail && crits.length > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">⚖ Score breakdown <span className="font-normal text-muted-foreground">· {detail.company_name}</span></div>
            <div className="space-y-2">
              {crits.map(([k, v]) => (
                <div key={k} className="flex items-center gap-3 text-[12px]">
                  <span className="w-44 shrink-0 text-muted-foreground">{k}</span>
                  <div className="h-[6px] flex-1 overflow-hidden rounded bg-muted/40">
                    <div className="h-full rounded" style={{ width: `${Math.round(v * 100)}%`, background: "linear-gradient(90deg,#0b7c74,#4ecdc2)" }} />
                  </div>
                  <span className="w-9 shrink-0 text-right font-mono">{v.toFixed(2).replace(/^0/, "")}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-xl border border-teal-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">◈ Evidence (top 3)</div>
              <div className="space-y-1.5 text-[12px]">
                {detail.evidence.slice(0, 3).map((e, i) => (
                  <div key={i} className="flex gap-2"><span className="font-mono text-[10px] text-teal-700 dark:text-teal-300">{EV_LABEL[e.kind] ?? e.kind}</span><span className="text-muted-foreground">{e.ref}</span></div>
                ))}
                {detail.evidence.length === 0 && <div className="text-muted-foreground">No evidence yet — score this lead.</div>}
              </div>
            </div>
            <div className="rounded-xl border border-purple-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">👥 Who decides</div>
              <div className="space-y-1 text-[12px]">
                {detail.buying_group.map((m, i) => (
                  <div key={i} className="flex justify-between"><span className="text-muted-foreground">{ROLE_LABEL[m.role] ?? m.role}</span><span>{m.name}</span></div>
                ))}
                {detail.buying_group.length === 0 && <div className="text-muted-foreground">—</div>}
              </div>
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-card/60 p-4">
              <div className="mb-2 text-sm font-semibold">→ Suggested next step</div>
              <p className="text-[12px] text-muted-foreground">{detail.recommended_action} · consent {detail.consent_status || "—"}.</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Account priority table ──────────────── */}
      {items && (
        <div className="rounded-xl border bg-card/60 p-4">
          <div className="mb-3 text-sm font-semibold">◷ Accounts to work next <span className="font-normal text-muted-foreground">· all leads</span></div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="pb-2 pr-3 font-medium">Company</th><th className="pb-2 pr-3 font-medium">Industry</th>
                <th className="pb-2 pr-3 font-medium">Score</th><th className="pb-2 pr-3 font-medium">Intent</th>
                <th className="pb-2 pr-3 font-medium">Consent</th><th className="pb-2 pr-3 font-medium">Who decides</th>
                <th className="pb-2 pr-3 font-medium">Source</th><th className="pb-2 pr-3 font-medium">Next step</th><th className="pb-2 font-medium"></th>
              </tr></thead>
              <tbody className="divide-y divide-border">
                {items.length === 0 && <tr><td colSpan={9} className="py-4 text-muted-foreground">No leads yet.</td></tr>}
                {items.map((l) => (
                  <tr key={l.id} onClick={() => select(l.id)} className={`cursor-pointer ${detail?.id === l.id ? "bg-primary/5" : ""}`}>
                    <td className="py-2.5 pr-3 font-medium">{l.company_name}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.sector || "—"}</td>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-2">
                        <div className="h-[5px] w-14 overflow-hidden rounded bg-muted/40"><div className="h-full" style={{ width: `${Math.round(l.score * 100)}%`, background: "linear-gradient(90deg,#0b7c74,#4ecdc2)" }} /></div>
                        <span className="font-mono text-xs">{l.score.toFixed(2)}</span>
                      </div>
                    </td>
                    <td className="py-2.5 pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] ${INTENT[l.intent] ?? ""}`}>{l.intent}</span></td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.consent_status || "—"}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.buying_group_count} {l.buying_group_count === 1 ? "role" : "roles"}</td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-muted-foreground">{l.source || "—"}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">{l.recommended_action}</td>
                    <td className="py-2.5"><button onClick={(e) => { e.stopPropagation(); score(l.id); }} className="rounded-md border px-2.5 py-1 text-[11px]">Score</button></td>
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
