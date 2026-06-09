/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Growth Context Graph. Faithful to mockup 05: scorecards, a
// radial node-link canvas (a company's ego-network — canonical company at the
// centre, its leads / contacts / opportunities around it), and a right rail
// with the entity inspector, the entity-resolution pipeline and the Graph-RAG
// retrieval flow. GET /v1/context-graph + POST /resolve.
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Node = { id: string; type: string; label: string; lifecycle?: string; score?: number; merged_count?: number };
type Edge = { source: string; target: string; rel: string };
type Stats = { companies: number; nodes: number; edges: number; match_accuracy: number; merges: number };
type Data = { nodes: Node[]; edges: Edge[]; stats: Stats };

const TYPE_BORDER: Record<string, string> = {
  company: "border-[rgba(58,157,255,.5)] text-sky-200",
  lead: "border-[rgba(210,153,34,.5)] text-amber-200",
  contact: "border-border text-foreground",
  opportunity: "border-[rgba(63,185,80,.5)] text-emerald-200",
};
const TYPE_LABEL: Record<string, string> = {
  company: "Company · canonical", lead: "Lead · hot", contact: "Contact", opportunity: "Opportunity",
};

const ER_STEPS = [
  "Normalize · TR-aware (A.Ş./Ltd. ayrıştır)",
  "Blocking · VKN + domain k-NN",
  "Deterministic · VKN/email tam eşleşme",
  "Fuzzy · Jaro-Winkler + adres",
  "Embedding · BGE-M3 cosine",
  "Canonical · survivorship (ERP>CRM>web)",
  "Human-in-loop · düşük-güven review",
];

export default function ContextGraphPage() {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch("/v1/context-graph", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Data) => setD(j)).catch((e) => setErr(String(e)));
  }, []);
  useEffect(load, [load]);

  async function resolve() {
    setBusy(true);
    try {
      await fetch("/v1/context-graph/resolve", { method: "POST", credentials: "include" });
      load();
    } finally { setBusy(false); }
  }

  // Ego-network: the company with the most neighbours becomes the centre.
  const layout = useMemo(() => {
    if (!d || d.nodes.length === 0) return null;
    const byId = new Map(d.nodes.map((n) => [n.id, n]));
    const degree = new Map<string, number>();
    for (const e of d.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    const companies = d.nodes.filter((n) => n.type === "company");
    const center = companies.sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0))[0] ?? d.nodes[0];
    const neighborIds = d.edges.filter((e) => e.source === center.id).map((e) => e.target)
      .concat(d.edges.filter((e) => e.target === center.id).map((e) => e.source));
    const neighbors = Array.from(new Set(neighborIds)).map((id) => byId.get(id)).filter(Boolean) as Node[];
    // other companies become secondary peripheral nodes for context.
    const others = companies.filter((c) => c.id !== center.id).slice(0, 4);
    const ring = [...neighbors, ...others];
    const placed = ring.map((n, i) => {
      const ang = (-90 + (360 / Math.max(ring.length, 1)) * i) * (Math.PI / 180);
      return { node: n, left: 50 + 34 * Math.cos(ang), top: 48 + 36 * Math.sin(ang),
               highlight: n.type === "lead" || n.type === "opportunity" };
    });
    return { center, placed };
  }, [d]);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Growth Context Graph</h1>
          <p className="mt-1 text-[12px] text-muted-foreground">CRM + ERP + web tek canonical node&apos;a birleşir · entity resolution · 1-2 hop graph-RAG · tenant-scoped</p>
        </div>
        <button onClick={resolve} disabled={busy} className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50">{busy ? "Çalışıyor…" : "⚖ Entity Resolution çalıştır"}</button>
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Yüklenemedi: {err}</div>}
      {!d && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {d && (
        <>
          {/* ── Scorecards ─────────────────────────── */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              ["Entity", String(d.stats.nodes), "Company · Account · Contact · Lead · Opp…"],
              ["İlişki (edge)", String(d.stats.edges), "valid-time · merge geçmişi"],
              ["ER merge (bekleyen)", String(d.stats.merges), "düşük-güven → review kuyruğu"],
              ["Match accuracy", `%${Math.round(d.stats.match_accuracy * 100)}`, "canonical entity · TR-aware"],
            ].map(([l, v, h]) => (
              <div key={l} className="rounded-xl border bg-card/60 p-4">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div>
                <div className="mt-1 font-mono text-2xl font-semibold">{v}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">{h}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* ── Radial graph canvas ──────────────── */}
            <div className="rounded-xl border bg-card/60 p-3 lg:col-span-2">
              <div className="relative h-[440px] overflow-hidden rounded-xl border"
                style={{ background: "radial-gradient(circle at 50% 45%, rgba(58,157,255,.06), transparent 65%)" }}>
                {!layout && <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Henüz entity yok.</div>}
                {layout && (
                  <>
                    <svg className="pointer-events-none absolute inset-0 h-full w-full">
                      {layout.placed.map((p, i) => (
                        <line key={i} x1="50%" y1="48%" x2={`${p.left}%`} y2={`${p.top}%`}
                          stroke={p.highlight ? "#3a9dff" : "rgba(118,138,154,.3)"}
                          strokeWidth={p.highlight ? 2 : 1.5}
                          strokeDasharray={p.node.type === "contact" || p.node.type === "company" ? "4 4" : undefined} />
                      ))}
                    </svg>
                    {/* peripheral nodes */}
                    {layout.placed.map((p) => (
                      <GraphNode key={p.node.id} left={p.left} top={p.top} type={p.node.type} label={p.node.label} />
                    ))}
                    {/* centre */}
                    <GraphNode left={50} top={48} type={layout.center.type} label={layout.center.label} center />
                  </>
                )}
              </div>
            </div>

            {/* ── Right rail ───────────────────────── */}
            <div className="space-y-6">
              {layout && (
                <div className="rounded-xl border bg-card/60 p-4" style={{ boxShadow: "inset 0 2px 0 0 rgba(58,157,255,.5)" }}>
                  <div className="mb-3 text-sm font-semibold">⬡ {layout.center.label}</div>
                  <div className="space-y-0 text-[12px]">
                    {[
                      ["Canonical match", (d.stats.match_accuracy).toFixed(2)],
                      ["Kaynak", "ERP+CRM+web"],
                      ["Birleşen kayıt", `${layout.center.merged_count ?? 1} → 1`],
                      ["VKN", "deterministik ✓"],
                      ["Lifecycle", layout.center.lifecycle ?? "lead"],
                      ["Buying group", `${layout.placed.filter((p) => p.node.type === "contact").length || 1} rol`],
                    ].map(([k, v]) => (
                      <div key={k} className="flex justify-between border-b border-border py-1.5 last:border-0">
                        <span className="text-muted-foreground">{k}</span><span className="font-mono">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border bg-card/60 p-4">
                <div className="mb-3 text-sm font-semibold">⚖ Entity Resolution</div>
                <ol className="space-y-1.5 text-[12px] text-muted-foreground">
                  {ER_STEPS.map((s, i) => (
                    <li key={i} className="flex gap-2"><span className="font-mono text-primary">{i + 1}</span><span>{s}</span></li>
                  ))}
                </ol>
              </div>

              <div className="rounded-xl border bg-card/60 p-4">
                <div className="mb-2 text-sm font-semibold">▦ Graph-RAG retrieval</div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  sorgu → Qdrant top-k chunk → entity-mention → 1-2 hop subgraph → rerank → LLM (chunk + subgraph) →{" "}
                  <span className="text-foreground">kaynak + entity cite</span>
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function GraphNode({ left, top, type, label, center }: {
  left: number; top: number; type: string; label: string; center?: boolean;
}) {
  return (
    <div
      className={`absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-[9px] border bg-[#131920] px-2.5 py-1.5 text-center text-[11px] font-medium ${TYPE_BORDER[type] ?? "border-border"} ${center ? "shadow-[0_0_18px_rgba(58,157,255,.25)]" : ""}`}
      style={{ left: `${left}%`, top: `${top}%`, zIndex: center ? 10 : 1 }}
    >
      <span className="block font-mono text-[8.5px] uppercase tracking-wide text-muted-foreground">{TYPE_LABEL[type] ?? type}</span>
      {label}
    </div>
  );
}
