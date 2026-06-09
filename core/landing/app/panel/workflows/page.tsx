/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Workflow Designer (Stage D: real interactive editor).
// The canvas is a live xyflow graph: drag nodes, drag handle→handle to wire or
// rewire, Delete to remove, click an agent node to inspect. "Kaydet" persists
// the graph (positions + edges); "Çalıştır" saves then runs the agent chain in
// the graph's topological order. GET/PUT /definition, GET palette/agents/runs,
// POST run.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import AgenticFlowCanvas, { type FlowNodeData } from "@/components/AgenticFlowCanvas";

type AgentDetail = {
  id: string; name: string; model: string; tools: string[];
  risk: string; output_kind: string; requires_approval: boolean;
};
type PaletteAgent = { id: string; name: string; risk: string };
type Palette = { node_kinds: string[]; agents: Record<string, PaletteAgent[]> };
type Run = {
  id: number; name: string; trigger: string; status: string;
  step_count: number; approvals_opened: number; elapsed_ms: number; created_at: string | null;
};
type GraphNode = { id: string; kind: string; name: string; desc: string; x: number; y: number; agent_id: string | null };
type GraphEdge = { source: string; target: string };
type Definition = { key: string; name: string; graph: { name: string; nodes: GraphNode[]; edges: GraphEdge[] }; ordered_steps: string[] };

const KIND_CHIP: Record<string, string> = {
  trigger: "border-sky-500/40 text-sky-300", agent: "border-primary/50 text-primary",
  retrieval: "border-violet-500/40 text-violet-300", connector: "border-border text-muted-foreground",
  policy: "border-amber-500/40 text-amber-300", approval: "border-rose-500/40 text-rose-300",
  action: "border-emerald-500/40 text-emerald-300", branch: "border-border text-muted-foreground",
  sub_workflow: "border-pink-500/40 text-pink-300",
};

const ENGINE = [
  "State checkpoint (SQLite)", "Retry + timeout + compensation",
  "Human-approval pause / resume", "Step-level audit + tool history",
  "LangGraph (multi-agent) · gerektiğinde",
];

const KIND_LABEL: Record<string, string> = {
  trigger: "Tetikleyici", retrieval: "RAG/Graph", connector: "Connector",
  policy: "Policy Gate", approval: "Onay Geçidi", action: "Aksiyon",
  branch: "Dallanma", sub_workflow: "Alt-akış",
};

function toFlowNodes(g: Definition["graph"]): Node<FlowNodeData>[] {
  return g.nodes.map((n) => ({
    id: n.id, type: "agentic", position: { x: n.x, y: n.y },
    data: { kind: n.kind, name: n.name, desc: n.desc, agent_id: n.agent_id },
  }));
}
function toFlowEdges(g: Definition["graph"]): Edge[] {
  return g.edges.map((e) => ({ id: `e-${e.source}-${e.target}`, source: e.source, target: e.target }));
}

export default function WorkflowDesignerPage() {
  const [agents, setAgents] = useState<Record<string, AgentDetail>>({});
  const [palette, setPalette] = useState<Palette | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("Inbound → Cevap Taslağı");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const idc = useRef(0);

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
    fetch("/v1/agentic-workflows/definition", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Definition) => {
        setName(d.graph.name || d.name);
        setNodes(toFlowNodes(d.graph));
        setEdges(toFlowEdges(d.graph));
        const firstAgent = d.graph.nodes.find((n) => n.kind === "agent");
        setSelected(firstAgent?.id ?? null);
      }).catch((e) => setErr(String(e)));
    loadRuns();
  }, [loadRuns, setNodes, setEdges]);

  const onConnect = useCallback((c: Connection) => {
    setEdges((eds) => addEdge({ ...c, id: `e-${c.source}-${c.target}` }, eds));
    setSaved(null);
  }, [setEdges]);

  const onNodeClick = useCallback((id: string) => setSelected(id), []);

  function addNode(kind: string, agent_id: string | null, label: string, desc: string) {
    const id = `${kind}-${(idc.current += 1)}`;
    setNodes((nds) => nds.concat({
      id, type: "agentic",
      position: { x: 120 + (nds.length % 4) * 30, y: 360 + (nds.length % 3) * 20 },
      data: { kind, name: label, desc, agent_id },
    }));
    setSelected(agent_id ? id : selected);
    setSaved(null);
  }

  function currentGraph() {
    return {
      name,
      nodes: nodes.map((n) => ({
        id: n.id, kind: n.data.kind, name: n.data.name, desc: n.data.desc,
        x: Math.round(n.position.x), y: Math.round(n.position.y), agent_id: n.data.agent_id,
      })),
      edges: edges.map((e) => ({ source: e.source, target: e.target })),
    };
  }

  async function save(): Promise<string[]> {
    const r = await fetch("/v1/agentic-workflows/definition", {
      method: "PUT", credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ key: "default", name, graph: currentGraph() }),
    });
    const j = await r.json();
    setSaved(`${j.node_count} node · ${j.edge_count} bağlantı kaydedildi`);
    return j.ordered_steps ?? [];
  }

  async function onSave() {
    setBusy(true);
    try { await save(); } finally { setBusy(false); }
  }

  async function run(dry = false) {
    setBusy(true); setErr(null);
    try {
      const steps = await save();
      if (steps.length === 0) { setErr("Çalıştırılacak agent node yok — palette'ten bir agent ekleyin."); return; }
      const r = await fetch("/v1/agentic-workflows/run", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, steps, input: "Fiyat öğrenmek istiyorum", trigger: "web form", dry_run: dry }),
      });
      if (dry) {
        const j = await r.json();
        setSaved(`Dry-run: ${j.steps_run}/${j.step_count} adım çalıştı · ${j.would_open_approvals} onay açılırdı (kalıcı etki yok)`);
      } else {
        loadRuns();
      }
    } finally { setBusy(false); }
  }

  const flowNodes = nodes.map((n) => ({ ...n, selected: n.id === selected }));
  const sel = selected ? agents[nodes.find((n) => n.id === selected)?.data.agent_id ?? ""] : undefined;
  const selNode = nodes.find((n) => n.id === selected);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Workflow Designer · <span className="text-muted-foreground">&quot;{name}&quot;</span></h1>
          <p className="mt-1 text-[12px] text-muted-foreground">interaktif · sürükle-bağla · event-triggered · human-approval-pause · state + retry + rollback</p>
        </div>
        <div className="flex items-center gap-2">
          {saved && <span className="text-[11px] text-emerald-300/80">✓ {saved}</span>}
          <button onClick={onSave} disabled={busy} className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50" data-test="wf-save">Kaydet</button>
          <button onClick={() => run(true)} disabled={busy} className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50" data-test="wf-dryrun">Dry-run</button>
          <button onClick={() => run(false)} disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow disabled:opacity-50" data-test="wf-run">{busy ? "Çalışıyor…" : "▶ Çalıştır"}</button>
        </div>
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">{err}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Main: interactive canvas + run history ─────────── */}
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-semibold">◆ Canvas <span className="font-normal text-muted-foreground">· sürükle · handle&apos;dan handle&apos;a bağla · Delete ile sil</span></div>
            </div>
            <AgenticFlowCanvas
              nodes={flowNodes}
              edges={edges}
              onNodesChange={(c) => { onNodesChange(c); if (c.some((x) => x.type === "position" || x.type === "remove")) setSaved(null); }}
              onEdgesChange={(c) => { onEdgesChange(c); if (c.some((x) => x.type === "remove")) setSaved(null); }}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
            />
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
            <div className="mb-3 text-sm font-semibold">⚡ Node: {selNode?.data.name ?? "—"}</div>
            {selNode?.data.kind === "agent" && sel ? (
              <div className="space-y-0 text-[12px]">
                {[
                  ["Tür", "Agent step"],
                  ["Model", sel.model || "—"],
                  ["Allowed tools", (sel.tools ?? []).join(" · ") || "—"],
                  ["Output schema", sel.output_kind || "—"],
                  ["Risk", sel.risk || "—"],
                  ["Onay kuralı", sel.requires_approval ? "gönderim öncesi" : "otomatik"],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-border py-1.5 last:border-0">
                    <span className="text-muted-foreground">{k}</span><span className="font-mono text-right">{v}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-muted-foreground">
                {selNode ? `${KIND_LABEL[selNode.data.kind] ?? selNode.data.kind} node — ${selNode.data.desc}` : "Canvas'ta bir node'a tıklayın."}
              </div>
            )}
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-2 text-sm font-semibold">⊞ Node Ekle</div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Yapı</div>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(palette?.node_kinds ?? []).filter((k) => k !== "agent").map((k) => (
                <button key={k} onClick={() => addNode(k, null, KIND_LABEL[k] ?? k, "")}
                  className={`rounded-md border px-2 py-1 text-[11px] capitalize hover:bg-muted/40 ${KIND_CHIP[k] ?? "border-border text-muted-foreground"}`}
                  data-test={`palette-${k}`}>+ {k.replace("_", "-")}</button>
              ))}
            </div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Agent</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.values(palette?.agents ?? {}).flat().slice(0, 10).map((a) => (
                <button key={a.id} onClick={() => addNode("agent", a.id, a.name, a.risk + " risk")}
                  className="rounded-md border border-primary/40 px-2 py-1 text-[11px] text-primary hover:bg-primary/10"
                  data-test={`palette-agent-${a.id}`}>+ {a.name}</button>
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
