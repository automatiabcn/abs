/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Workflow Designer (Stage D: real interactive editor).
// The canvas is a live xyflow graph: drag nodes, drag handle→handle to wire or
// rewire, Delete to remove, click an agent node to inspect. "Save" persists
// the graph (positions + edges); "Run" saves then runs the agent chain in
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
type NodeConfig = Record<string, string | number | boolean>;
type GraphNode = { id: string; kind: string; name: string; desc: string; x: number; y: number; agent_id: string | null; config?: NodeConfig };
type GraphEdge = { source: string; target: string };
type Definition = { key: string; name: string; graph: { name: string; nodes: GraphNode[]; edges: GraphEdge[] }; ordered_steps: string[] };

const KIND_CHIP: Record<string, string> = {
  trigger: "border-sky-500/40 text-sky-700 dark:text-sky-300", agent: "border-primary/50 text-primary",
  retrieval: "border-violet-500/40 text-violet-700 dark:text-violet-300", connector: "border-border text-muted-foreground",
  policy: "border-amber-500/40 text-amber-700 dark:text-amber-300", approval: "border-rose-500/40 text-rose-700 dark:text-rose-300",
  action: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300", branch: "border-border text-muted-foreground",
  sub_workflow: "border-pink-500/40 text-pink-700 dark:text-pink-300", custom_ai: "border-primary/50 text-primary",
  consent: "border-amber-500/40 text-amber-700 dark:text-amber-300",
};

const ENGINE = [
  "Picks up where it left off after a restart", "Retries, times out, and rolls back",
  "Pauses for your approval, resumes on your click", "Every step and tool call is logged",
  "Runs several agents together when a step needs it",
];

const KIND_LABEL: Record<string, string> = {
  trigger: "Trigger", retrieval: "Knowledge", connector: "Connector",
  policy: "Policy check", consent: "Consent", approval: "Approval", action: "Action",
  branch: "Branch", sub_workflow: "Sub-workflow", custom_ai: "Custom AI",
};

// Per-kind editable config fields rendered in the inspector. `as` picks the
// input control; options are for selects. Empty for kinds with no config.
type CfgField = { key: string; label: string; as?: "text" | "textarea" | "number" | "select"; options?: string[]; placeholder?: string };
const CONFIG_FIELDS: Record<string, CfgField[]> = {
  custom_ai: [
    { key: "instruction", label: "What should this step do?", as: "textarea", placeholder: "In plain English. E.g. Draft a quote for the customer and cite the price list." },
  ],
  retrieval: [
    // Rendered as a picker bound to the Context Graph's companies (see inspector).
    { key: "scope_company", label: "Focus on a company (optional)", as: "select" },
    { key: "query", label: "What to look up (blank = the previous step)", as: "text", placeholder: "price list" },
    { key: "top_k", label: "How many results", as: "number", placeholder: "5" },
  ],
  policy: [
    { key: "risk_threshold", label: "Stop at this risk level", as: "select", options: ["low", "medium", "high"] },
  ],
  consent: [
    { key: "channel", label: "Channel", as: "select", options: ["any", "email", "whatsapp", "sms"] },
  ],
  approval: [
    { key: "role", label: "Who approves", as: "select", options: ["admin", "manager", "owner"] },
  ],
  action: [
    { key: "action_type", label: "What to do", as: "select", options: ["note", "email", "route", "crm_update"] },
    // Target is a picker bound to real things: a graph company for note/crm_update,
    // a channel for email/route (see inspector — options follow action_type).
    { key: "target", label: "Where it goes", as: "select" },
  ],
  connector: [
    // Rendered as a picker bound to the tenant's real connectors (see inspector).
    { key: "connector_id", label: "Which connector to sync", as: "select" },
  ],
};

function toFlowNodes(g: Definition["graph"]): Node<FlowNodeData>[] {
  return g.nodes.map((n) => ({
    id: n.id, type: "agentic", position: { x: n.x, y: n.y },
    data: { kind: n.kind, name: n.name, desc: n.desc, agent_id: n.agent_id, config: n.config ?? {} },
  }));
}
function toFlowEdges(g: Definition["graph"]): Edge[] {
  return g.edges.map((e) => ({ id: `e-${e.source}-${e.target}`, source: e.source, target: e.target }));
}

export default function WorkflowDesignerPage() {
  const [agents, setAgents] = useState<Record<string, AgentDetail>>({});
  const [palette, setPalette] = useState<Palette | null>(null);
  const [connectors, setConnectors] = useState<{ id: string; name: string; has_adapter: boolean }[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("Incoming message → draft reply");
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
    // A Connector step binds to a real connector, so the inspector offers the
    // tenant's actual connectors instead of a free-text id nobody can get right.
    fetch("/v1/connectors", { credentials: "include", cache: "no-store" })
      .then((r) => r.json())
      .then((j: { groups?: { connectors: { id: string; name: string; has_adapter: boolean }[] }[] }) =>
        setConnectors((j.groups ?? []).flatMap((g) => g.connectors)))
      .catch(() => {});
    // Companies from the Context Graph: a Retrieval step can focus on one, and
    // an Action step can file its note/update against a real record.
    fetch("/v1/context-graph", { credentials: "include", cache: "no-store" })
      .then((r) => r.json())
      .then((j: { nodes?: { type: string; label: string }[] }) =>
        setCompanies((j.nodes ?? []).filter((n) => n.type === "company").map((n) => n.label)))
      .catch(() => {});
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
    const config: NodeConfig = {};
    (CONFIG_FIELDS[kind] ?? []).forEach((f) => { config[f.key] = f.as === "number" ? 0 : (f.options?.[0] ?? ""); });
    // The tail of the chain: the last node nothing flows out of. A new step is
    // dropped just to its right and wired onto the end automatically, so the
    // flow reads left→right and a person never has to discover the connect
    // handles to make their step actually run (an unwired step is skipped).
    const sources = new Set(edges.map((e) => e.source));
    const tail = [...nodes].reverse().find((n) => !sources.has(n.id)) ?? nodes[nodes.length - 1];
    const pos = tail
      ? { x: tail.position.x + 210, y: tail.position.y }
      : { x: 120, y: 200 };
    setNodes((nds) => nds.concat({
      id, type: "agentic", position: pos,
      data: { kind, name: label, desc, agent_id, config },
    }));
    if (tail) setEdges((eds) => addEdge({ source: tail.id, target: id, id: `e-${tail.id}-${id}` }, eds));
    setSelected(id);   // open the inspector so the new node can be configured
    setSaved(null);
  }

  // Patch the selected node's config (editable inspector) — live state update.
  function updateNodeConfig(id: string, key: string, value: string | number) {
    setNodes((nds) => nds.map((n) => n.id === id
      ? { ...n, data: { ...n.data, config: { ...(n.data.config ?? {}), [key]: value } } }
      : n));
    setSaved(null);
  }

  function currentGraph() {
    return {
      name,
      nodes: nodes.map((n) => ({
        id: n.id, kind: n.data.kind, name: n.data.name, desc: n.data.desc,
        x: Math.round(n.position.x), y: Math.round(n.position.y), agent_id: n.data.agent_id,
        config: n.data.config ?? {},
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
    setSaved(`Saved · ${j.node_count} steps, ${j.edge_count} connections`);
    return j.ordered_steps ?? [];
  }

  async function onSave() {
    setBusy(true);
    try { await save(); } finally { setBusy(false); }
  }

  async function run(dry = false) {
    setBusy(true); setErr(null);
    try {
      await save();
      const graph = currentGraph();
      const wired = new Set<string>();
      graph.edges.forEach((e) => { wired.add(e.source); wired.add(e.target); });
      const runnable = graph.nodes.filter(
        (n) => n.kind !== "trigger" && (graph.nodes.length === 1 || wired.has(n.id)),
      );
      if (runnable.length === 0) {
        setErr("Nothing to run. Add a step from the palette and connect it.");
        return;
      }
      // Send the whole graph: the engine runs every wired node (agent, retrieval,
      // policy, consent, approval, action), not only the agent nodes.
      const r = await fetch("/v1/agentic-workflows/run", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, graph, input: "I would like to know the price", trigger: "web form", dry_run: dry }),
      });
      if (dry) {
        const j = await r.json();
        setSaved(`Test run: ${j.steps_run}/${j.step_count} steps ran · ${j.would_open_approvals} approvals would open · nothing was changed`);
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
          <p className="mt-1 text-[12px] text-muted-foreground">Drag steps, connect them, run. It pauses for your approval and picks up where it left off.</p>
        </div>
        <div className="flex items-center gap-2">
          {saved && <span className="text-[11px] text-emerald-700 dark:text-emerald-300/80">✓ {saved}</span>}
          <button onClick={onSave} disabled={busy} className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50" data-test="wf-save">Save</button>
          <button onClick={() => run(true)} disabled={busy} className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-50" data-test="wf-dryrun">Test run</button>
          <button onClick={() => run(false)} disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow disabled:opacity-50" data-test="wf-run">{busy ? "Running…" : "▶ Run"}</button>
        </div>
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">{err}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Main: interactive canvas + run history ─────────── */}
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-semibold">◆ Canvas <span className="font-normal text-muted-foreground">· steps run left → right · a new step joins the end on its own · drag a dot to another step to rewire · Delete to remove</span></div>
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
            <div className="mb-3 text-sm font-semibold">◍ Past runs <span className="font-normal text-muted-foreground">· every retry and rollback is recorded</span></div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">Run</th><th className="pb-2 pr-3 font-medium">Trigger</th>
                  <th className="pb-2 pr-3 font-medium">Steps</th><th className="pb-2 pr-3 font-medium">Took</th><th className="pb-2 font-medium">Status</th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {runs.length === 0 && <tr><td colSpan={5} className="py-3 text-muted-foreground">Nothing has run yet.</td></tr>}
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td className="py-2.5 pr-3 font-mono text-xs">#{r.id} {r.name}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{r.trigger || "manual"}</td>
                      <td className="py-2.5 pr-3 font-mono">{r.step_count}</td>
                      <td className="py-2.5 pr-3 font-mono text-muted-foreground">{(r.elapsed_ms / 1000).toFixed(1)}s</td>
                      <td className="py-2.5"><span className={r.status === "done" ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300"}>{r.status}{r.approvals_opened > 0 ? ` · ${r.approvals_opened} waiting for approval` : ""}</span></td>
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
            <div className="mb-3 text-sm font-semibold">⚡ Step: {selNode?.data.name ?? "—"}</div>
            {selNode?.data.kind === "agent" && sel ? (
              <div className="space-y-0 text-[12px]">
                {[
                  ["Type", "Agent step"],
                  ["Model", sel.model || "—"],
                  ["Tools it may use", (sel.tools ?? []).join(" · ") || "—"],
                  ["Answer format", sel.output_kind || "—"],
                  ["Risk", sel.risk || "—"],
                  ["Approval", sel.requires_approval ? "asks you before sending" : "runs on its own"],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-border py-1.5 last:border-0">
                    <span className="text-muted-foreground">{k}</span><span className="font-mono text-right">{v}</span>
                  </div>
                ))}
              </div>
            ) : selNode && (CONFIG_FIELDS[selNode.data.kind]?.length ?? 0) > 0 ? (
              <div className="space-y-3 text-[12px]">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {KIND_LABEL[selNode.data.kind] ?? selNode.data.kind} · settings
                </div>
                {CONFIG_FIELDS[selNode.data.kind].map((f) => {
                  const val = (selNode.data.config ?? {})[f.key] ?? "";
                  const cls = "w-full rounded-md border border-border bg-background px-2 py-1 text-[12px]";
                  return (
                    <label key={f.key} className="block space-y-1">
                      <span className="text-muted-foreground">{f.label}</span>
                      {f.as === "textarea" ? (
                        <textarea className={`${cls} min-h-[72px]`} placeholder={f.placeholder} value={String(val)}
                          onChange={(e) => updateNodeConfig(selNode.id, f.key, e.target.value)} data-test={`cfg-${f.key}`} />
                      ) : f.key === "connector_id" ? (
                        // Bind the box to a real connector, not a hand-typed id.
                        connectors.length === 0 ? (
                          <a href="/panel/connectors" className="block rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-muted-foreground hover:text-foreground">
                            No connectors yet — set one up first ↗
                          </a>
                        ) : (
                          <>
                            <select className={cls} value={String(val)}
                              onChange={(e) => updateNodeConfig(selNode.id, f.key, e.target.value)} data-test="cfg-connector_id">
                              <option value="">Pick a connector…</option>
                              {connectors.map((c) => (
                                <option key={c.id} value={c.id}>{c.name}{c.has_adapter ? " · syncs now" : " · roadmap"}</option>
                              ))}
                            </select>
                            {val && !connectors.find((c) => c.id === val)?.has_adapter && (
                              <span className="text-[10px] text-amber-600 dark:text-amber-400">This connector has no live sync yet — the step will be skipped until it does.</span>
                            )}
                          </>
                        )
                      ) : f.key === "scope_company" ? (
                        // Narrow retrieval to one real company from the graph.
                        companies.length === 0 ? (
                          <a href="/panel/graph" className="block rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-muted-foreground hover:text-foreground">
                            No companies in the graph yet — import data first ↗
                          </a>
                        ) : (
                          <select className={cls} value={String(val)}
                            onChange={(e) => updateNodeConfig(selNode.id, f.key, e.target.value)} data-test="cfg-scope_company">
                            <option value="">Everything (no focus)</option>
                            {companies.map((c) => (<option key={c} value={c}>{c}</option>))}
                          </select>
                        )
                      ) : f.key === "target" ? (
                        // Bind the action to a real destination — a graph company for a
                        // note/CRM update, a channel for an email/route.
                        (() => {
                          const at = String((selNode.data.config ?? {}).action_type ?? "note");
                          const toCompany = at === "note" || at === "crm_update";
                          const opts = toCompany ? companies : ["email", "whatsapp", "sms", "slack"];
                          if (toCompany && companies.length === 0) {
                            return (
                              <a href="/panel/graph" className="block rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-muted-foreground hover:text-foreground">
                                No companies in the graph yet — import data first ↗
                              </a>
                            );
                          }
                          return (
                            <>
                              <select className={cls} value={String(val)}
                                onChange={(e) => updateNodeConfig(selNode.id, f.key, e.target.value)} data-test="cfg-target">
                                <option value="">{toCompany ? "Pick a company…" : "Pick a channel…"}</option>
                                {opts.map((o) => (<option key={o} value={o}>{o}</option>))}
                              </select>
                              {!toCompany && (
                                <span className="text-[10px] text-muted-foreground">Recorded now; it sends once that channel is connected.</span>
                              )}
                            </>
                          );
                        })()
                      ) : f.as === "select" ? (
                        <select className={cls} value={String(val)}
                          onChange={(e) => updateNodeConfig(selNode.id, f.key, e.target.value)} data-test={`cfg-${f.key}`}>
                          {(f.options ?? []).map((o) => (<option key={o} value={o}>{o}</option>))}
                        </select>
                      ) : (
                        <input type={f.as === "number" ? "number" : "text"} className={cls} placeholder={f.placeholder} value={String(val)}
                          onChange={(e) => updateNodeConfig(selNode.id, f.key, f.as === "number" ? Number(e.target.value) : e.target.value)} data-test={`cfg-${f.key}`} />
                      )}
                    </label>
                  );
                })}
                <p className="text-[10px] text-muted-foreground">Save to keep these settings. The next run will use them.</p>
              </div>
            ) : (
              <div className="text-[11px] text-muted-foreground">
                {selNode ? `${KIND_LABEL[selNode.data.kind] ?? selNode.data.kind} step — ${selNode.data.desc || "nothing to configure"}` : "Click a step on the canvas."}
              </div>
            )}
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-2 text-sm font-semibold">⊞ Add a step</div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Steps</div>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(palette?.node_kinds ?? []).filter((k) => k !== "agent").map((k) => (
                <button key={k} onClick={() => addNode(k, null, KIND_LABEL[k] ?? k, "")}
                  className={`rounded-md border px-2 py-1 text-[11px] hover:bg-muted/40 ${KIND_CHIP[k] ?? "border-border text-muted-foreground"}`}
                  data-test={`palette-${k}`}>+ {KIND_LABEL[k] ?? k.replace("_", "-")}</button>
              ))}
            </div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Agents</div>
            {/* Every agent is reachable — a scroll cap keeps the rail short without
                hiding half the roster behind an arbitrary cut-off. */}
            <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto pr-1">
              {Object.values(palette?.agents ?? {}).flat().map((a) => (
                <button key={a.id} onClick={() => addNode("agent", a.id, a.name, a.risk + " risk")}
                  className="rounded-md border border-primary/40 px-2 py-1 text-[11px] text-primary hover:bg-primary/10"
                  data-test={`palette-agent-${a.id}`}>+ {a.name}</button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border bg-card/60 p-4">
            <div className="mb-3 text-sm font-semibold">⚙ What the engine handles</div>
            <ul className="space-y-1.5 text-[12px] text-muted-foreground">
              {ENGINE.map((e) => (<li key={e} className="flex items-start gap-2"><span className="text-emerald-400">✓</span><span>{e}</span></li>))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
