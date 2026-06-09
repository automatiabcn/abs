/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Workflow Designer. Faithful to mockup 03: a spatial node
// flow canvas (trigger → agent → retrieval → gate → agent → check → pause →
// action), a run-history table below, and a right rail with the node inspector,
// node palette and engine capabilities. Header runs the chain. GET palette +
// agents + runs, POST run.
"use client";

import { useCallback, useEffect, useState } from "react";

type AgentDetail = {
  id: string; name: string; model: string; tools: string[];
  risk: string; output_kind: string; requires_approval: boolean;
};
type Palette = { node_kinds: string[] };
type Run = {
  id: number; name: string; trigger: string; status: string;
  step_count: number; approvals_opened: number; elapsed_ms: number; created_at: string | null;
};

// The canonical demo chain shown in the canvas; the two agent nodes are
// selectable to drive the inspector.
const CHAIN = ["inbound_triage", "knowledge_base"];

const KIND_CHIP: Record<string, string> = {
  trigger: "border-sky-500/40 text-sky-300", agent: "border-primary/50 text-primary",
  retrieval: "border-violet-500/40 text-violet-300", connector: "border-border text-muted-foreground",
  policy: "border-amber-500/40 text-amber-300", approval: "border-rose-500/40 text-rose-300",
  action: "border-emerald-500/40 text-emerald-300", branch: "border-border text-muted-foreground",
  sub_workflow: "border-pink-500/40 text-pink-300",
};
const NODE_ACCENT: Record<string, string> = {
  agent: "border-[rgba(58,157,255,.45)] shadow-[0_0_14px_rgba(58,157,255,.12)]",
  amber: "border-[rgba(210,153,34,.5)]", green: "border-[rgba(63,185,80,.45)]",
};
const KIND_TEXT: Record<string, string> = { amber: "text-amber-300", green: "text-emerald-300" };

function FlowNode({ left, top, kind, name, desc, accent, active, onClick }: {
  left: number; top: number; kind: string; name: string; desc: string;
  accent?: string; active?: boolean; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`absolute w-[140px] rounded-[10px] border bg-[#131920] px-3 py-2.5 ${accent ? NODE_ACCENT[accent] : "border-border"} ${onClick ? "cursor-pointer" : ""} ${active ? "ring-2 ring-primary/60" : ""}`}
      style={{ left, top }}
    >
      <div className={`font-mono text-[9px] uppercase tracking-wider ${accent ? KIND_TEXT[accent] ?? "text-sky-300/80" : "text-muted-foreground"}`}>{kind}</div>
      <div className="mt-0.5 text-[12px] font-semibold">{name}</div>
      <div className="text-[10px] text-muted-foreground">{desc}</div>
    </div>
  );
}

const ENGINE = [
  "State checkpoint (SQLite)", "Retry + timeout + compensation",
  "Human-approval pause / resume", "Step-level audit + tool history",
  "LangGraph (multi-agent) · gerektiğinde",
];

export default function WorkflowDesignerPage() {
  const [agents, setAgents] = useState<Record<string, AgentDetail>>({});
  const [palette, setPalette] = useState<Palette | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string>("knowledge_base");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadRuns = useCallback(() => {
    fetch("/v1/agentic-workflows/runs", { credentials: "include", cache: "no-store" })
      .then((r) => r.json()).then((j: { runs: Run[] }) => setRuns(j.runs)).catch(() => {});
  }, []);
  useEffect(() => {
    fetch("/v1/agents", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: { categories: { agents: AgentDetail[] }[] }) => {
        const map: Record<string, AgentDetail> = {};
        for (const c of j.categories) for (const a of c.agents) map[a.id] = a;
        setAgents(map);
      }).catch((e) => setErr(String(e)));
    fetch("/v1/agentic-workflows/palette", { credentials: "include", cache: "no-store" })
      .then((r) => r.json()).then((j: Palette) => setPalette(j)).catch(() => {});
    loadRuns();
  }, [loadRuns]);

  const agentName = (id: string) => agents[id]?.name ?? id;
  const sel = agents[selected];

  async function run() {
    setBusy(true);
    try {
      await fetch("/v1/agentic-workflows/run", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: "Inbound → Cevap Taslağı", steps: CHAIN, input: "Fiyat öğrenmek istiyorum", trigger: "web form" }),
      });
      loadRuns();
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Workflow Designer · <span className="text-muted-foreground">&quot;Inbound → Cevap Taslağı&quot;</span></h1>
          <p className="mt-1 text-[12px] text-muted-foreground">event-triggered · human-approval-pause · state + retry + rollback</p>
        </div>
        <button onClick={run} disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow disabled:opacity-50">{busy ? "Çalışıyor…" : "▶ Çalıştır"}</button>
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Yüklenemedi: {err}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Main: canvas + run history ─────────── */}
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-xl border bg-card/60 p-4">
            <div className="overflow-x-auto">
              <div className="relative h-[300px] min-w-[800px] rounded-xl border"
                style={{ background: "radial-gradient(circle at 30% 20%, rgba(58,157,255,.06), transparent 60%)" }}>
                <svg className="pointer-events-none absolute inset-0 h-full w-full" style={{ overflow: "visible" }}>
                  <defs><linearGradient id="wfe" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#1e57ac" /><stop offset="100%" stopColor="#3a9dff" /></linearGradient></defs>
                  {[[146,145,162,143],[302,143,320,113],[302,143,320,233],[460,113,478,123],[460,233,478,235],[618,123,636,123],[618,235,636,235]].map(([x1,y1,x2,y2],i)=>(
                    <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="url(#wfe)" strokeWidth={2} opacity={0.55} />
                  ))}
                </svg>
                <FlowNode left={6} top={118} kind="Trigger" name="Inbound talep" desc="form · email · WhatsApp" />
                <FlowNode left={162} top={116} kind="⚡ Agent" name={agentName("inbound_triage")} desc="intent sınıflandırma" accent="agent" active={selected === "inbound_triage"} onClick={() => setSelected("inbound_triage")} />
                <FlowNode left={320} top={86} kind="Retrieval" name="RAG + Graph" desc="hybrid · cite" />
                <FlowNode left={320} top={206} kind="Gate" name="Policy Engine" desc="Cerbos · risk" />
                <FlowNode left={478} top={96} kind="⚡ Agent" name={agentName("knowledge_base")} desc="kaynak-gösteren taslak" accent="agent" active={selected === "knowledge_base"} onClick={() => setSelected("knowledge_base")} />
                <FlowNode left={478} top={208} kind="Check" name="Consent Ledger" desc="kanal izni" />
                <FlowNode left={636} top={96} kind="⏸ Human Pause" name="Approval Gate" desc="orta-risk → onay" accent="amber" />
                <FlowNode left={636} top={208} kind="Action" name="CRM Note + Route" desc="yönlendir" accent="green" />
              </div>
            </div>
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">◍ Workflow Run History <span className="font-normal text-muted-foreground">· state · retry · rollback izlenir</span></div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">Run</th><th className="pb-2 pr-3 font-medium">Trigger</th>
                  <th className="pb-2 pr-3 font-medium">Adım</th><th className="pb-2 pr-3 font-medium">Süre</th><th className="pb-2 font-medium">Durum</th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {runs.length === 0 && <tr><td colSpan={5} className="py-3 text-muted-foreground">Henüz çalıştırma yok.</td></tr>}
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td className="py-2.5 pr-3 font-mono text-xs">#{r.id} {r.name}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{r.trigger || "manual"}</td>
                      <td className="py-2.5 pr-3 font-mono">{r.step_count}</td>
                      <td className="py-2.5 pr-3 font-mono text-muted-foreground">{(r.elapsed_ms / 1000).toFixed(1)}s</td>
                      <td className="py-2.5"><span className={r.status === "done" ? "text-emerald-300" : "text-amber-300"}>{r.status}{r.approvals_opened > 0 ? ` · ${r.approvals_opened} onay` : ""}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── Right rail: inspector + palette + engine ── */}
        <div className="space-y-6">
          <div className="rounded-xl border bg-card/60 p-4" style={{ boxShadow: "inset 0 2px 0 0 rgba(58,157,255,.5)" }}>
            <div className="mb-3 text-sm font-semibold">⚡ Node: {sel?.name ?? selected}</div>
            <div className="space-y-0 text-[12px]">
              {[
                ["Tür", "Agent step"],
                ["Model", sel?.model ?? "—"],
                ["Allowed tools", (sel?.tools ?? []).join(" · ") || "—"],
                ["Output schema", sel?.output_kind ?? "—"],
                ["Risk", sel?.risk ?? "—"],
                ["Onay kuralı", sel?.requires_approval ? "gönderim öncesi" : "otomatik"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border py-1.5 last:border-0">
                  <span className="text-muted-foreground">{k}</span><span className="font-mono text-right">{v}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 text-[10px] text-muted-foreground">Canvas&apos;ta bir agent node&apos;una tıklayın</div>
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">⊞ Node Paleti</div>
            <div className="flex flex-wrap gap-1.5">
              {(palette?.node_kinds ?? []).map((k) => (
                <span key={k} className={`rounded-md border px-2 py-1 text-[11px] capitalize ${KIND_CHIP[k] ?? "border-border text-muted-foreground"}`}>{k.replace("_", "-")}</span>
              ))}
            </div>
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">⚙ Engine</div>
            <ul className="space-y-1.5 text-[12px] text-muted-foreground">
              {ENGINE.map((e) => (<li key={e} className="flex items-start gap-2"><span className="text-emerald-400">✓</span><span>{e}</span></li>))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
