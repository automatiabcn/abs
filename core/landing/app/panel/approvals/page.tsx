/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Approval Center. Faithful to mockup 04: tier scorecards,
// detailed approval cards (action + rationale + proposed message + RAG/Graph/
// consent/policy evidence, decide buttons on the right) and a queue table.
// GET /v1/approvals + POST /{id}/decide.
"use client";

import { useCallback, useEffect, useState } from "react";

type Evidence = { kind: string; ref: string };
type Item = {
  id: number; agent_id: string; action: string; rationale: string;
  evidence: Evidence[]; proposed_message: string; risk: string;
  consent_status: string; policy_result: string; status: string;
  target_company: string; channel: string; created_at: string | null;
};
type Tier = { low_auto: number; medium_pending: number; high_pending: number; accept_rate: number | null };
type Data = { items: Item[]; pending_total: number; by_risk: Record<string, number>; tier_stats?: Tier };
type Action = {
  id: number; approval_item_id: number | null; agent_id: string; action_kind: string;
  channel: string; target_company: string; target_contact: string; status: string;
  reason: string; created_at: string | null;
};
type Outbox = { items: Action[]; total: number; by_status: Record<string, number> };

const RISK: Record<string, string> = {
  low: "border-emerald-500/40 text-emerald-300",
  medium: "border-amber-500/40 text-amber-300",
  high: "border-rose-500/40 text-rose-300",
};
const ACTION_STATUS: Record<string, string> = {
  executed: "border-emerald-500/40 text-emerald-300",
  sent: "border-emerald-500/40 text-emerald-300",
  blocked: "border-rose-500/40 text-rose-300",
  failed: "border-amber-500/40 text-amber-300",
};
// What actually ran. An agent writing a file or running a command is not the
// same event as a CRM note, and the outbox used to call both "internal action".
const ACTION_KIND: Record<string, string> = {
  message_send: "message",
  agent_tool: "assistant action",
  internal: "internal",
};
// "sent" means the message left this server — the delivery path said so. It used
// to say "queued", into a queue nothing drained, and the message never went.
const STATUS_LABEL: Record<string, string> = {
  executed: "✓ done", sent: "✓ sent", blocked: "⛔ blocked",
  failed: "⚠ not sent", rejected: "✕ rejected",
};
function trTime(iso: string | null): string {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
}
function evGroups(ev: Evidence[]) {
  const g: Record<string, string[]> = {};
  for (const e of ev || []) (g[e.kind] ??= []).push(e.ref);
  return g;
}
const EV_TITLE: Record<string, string> = {
  rag: "EVIDENCE · DOCUMENTS", graph: "EVIDENCE · GRAPH", consent: "EVIDENCE · CONSENT", policy: "POLICY",
};

export default function ApprovalCenterPage() {
  const [d, setD] = useState<Data | null>(null);
  const [outbox, setOutbox] = useState<Outbox | null>(null);
  const [result, setResult] = useState<{ status: string; reason: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Id whose decision is in flight — disables that row's buttons so a
  // double-click can't fire the (often irreversible, outbound) action twice.
  const [pendingId, setPendingId] = useState<number | null>(null);
  // Outbox row currently being sent again.
  const [retryId, setRetryId] = useState<number | null>(null);

  const load = useCallback(() => {
    fetch("/v1/approvals?status=pending", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Data) => setD(j)).catch((e) => setErr(String(e)));
    fetch("/v1/approvals/outbox", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Outbox) => setOutbox(j)).catch(() => {});
  }, []);
  useEffect(load, [load]);

  async function decide(id: number, decision: "approve" | "reject" | "edit") {
    if (pendingId !== null) return; // a decision is already in flight
    setPendingId(id);
    setErr(null);
    try {
      const r = await fetch(`/v1/approvals/${id}/decide`, {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json().catch(() => null);
      if (j?.action) setResult({ status: j.action.status, reason: j.action.reason });
      else if (decision === "reject") setResult({ status: "rejected", reason: "nothing was done" });
      load();
    } catch (e) {
      setErr(`Could not send your decision: ${String(e)}`);
    } finally {
      setPendingId(null);
    }
  }

  // A mail server that was down for a minute should not cost you the message you
  // already approved. The row keeps everything needed to send it again.
  async function retry(id: number) {
    if (retryId !== null) return;
    setRetryId(id);
    setErr(null);
    try {
      const r = await fetch(`/v1/approvals/outbox/${id}/retry`, {
        method: "POST", credentials: "include",
      });
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new Error(j?.detail ?? `HTTP ${r.status}`);
      setResult({ status: j.status, reason: j.reason });
      load();
    } catch (e) {
      setErr(`Could not send it again: ${String(e)}`);
    } finally {
      setRetryId(null);
    }
  }

  // Approving fires the (often outbound: email/WhatsApp/CRM) action. Confirm
  // first so a stray click on a dense queue row can't silently send.
  function confirmApprove(it: Item) {
    const where = it.channel && it.channel !== "agent_tool" ? ` It will be sent over ${it.channel}.` : "";
    if (window.confirm(`Approve: "${it.action}".${where}`)) {
      decide(it.id, "approve");
    }
  }

  const detailed = (d?.items ?? []).filter((i) => i.rationale);
  const queue = (d?.items ?? []).filter((i) => !i.rationale);
  const t = d?.tier_stats;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Approval Center</h1>
          <p className="mt-1 text-[12px] text-muted-foreground">Nothing here has happened yet. Each row is something the assistant wants to do, with its reasoning, evidence and risk — it runs only if you say so.</p>
        </div>
        {d && (
          <div className="flex gap-2 text-[11px]">
            <span className="rounded-full border border-amber-500/40 px-3 py-1 text-amber-300">{d.pending_total} waiting</span>
            <span className="rounded-full border border-rose-500/40 px-3 py-1 text-rose-300">{d.by_risk.high ?? 0} high risk</span>
          </div>
        )}
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Could not load: {err}</div>}
      {result && (
        <div data-test="action-result" className={`mb-4 flex items-center justify-between rounded-lg border px-4 py-2.5 text-sm ${result.status === "blocked" ? "border-rose-500/40 bg-rose-500/5 text-rose-200" : result.status === "failed" ? "border-amber-500/40 bg-amber-500/5 text-amber-200" : result.status === "rejected" ? "border-border bg-muted/20 text-muted-foreground" : "border-emerald-500/40 bg-emerald-500/5 text-emerald-200"}`}>
          <span><b>Outcome:</b> {STATUS_LABEL[result.status] ?? result.status} · {result.reason}</span>
          <button onClick={() => setResult(null)} className="text-xs opacity-70 hover:opacity-100">dismiss</button>
        </div>
      )}
      {!d && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {d && (
        <>
          {/* ── Tier scorecards ─────────────────────── */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              ["Low — ran on its own", String(t?.low_auto ?? 0), "reading a report, looking something up"],
              ["Medium — waiting for you", String(t?.medium_pending ?? 0), "a drafted email, a file the assistant wants to write"],
              ["High — waiting for you", String(t?.high_pending ?? 0), "sending a message, running a command"],
              ["You approved", t?.accept_rate != null ? `${t.accept_rate}%` : "—", "of what was proposed"],
            ].map(([l, v, h]) => (
              <div key={l} className="rounded-xl border bg-card/60 p-4">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div>
                <div className="mt-1 font-mono text-2xl font-semibold">{v}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">{h}</div>
              </div>
            ))}
          </div>

          {/* ── Detailed approval cards ─────────────── */}
          <div className="space-y-4">
            {detailed.length === 0 && <div className="text-sm text-muted-foreground">Nothing is waiting for you.</div>}
            {detailed.map((it) => {
              const g = evGroups(it.evidence);
              return (
                <div
                  key={it.id}
                  data-test="approval-item"
                  data-approval-id={it.id}
                  className="rounded-xl border bg-card/60 p-4"
                >
                  <div className="flex gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-primary">{it.agent_id}</span>
                        <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] ${RISK[it.risk] ?? ""}`}>{it.risk} risk</span>
                        {it.consent_status && <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">consent: {it.consent_status}</span>}
                        <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">policy: {it.policy_result}</span>
                        <span className="ml-auto text-[11px] text-muted-foreground">{trTime(it.created_at)}</span>
                      </div>
                      <div className="mt-2 text-[13px]"><b>Aksiyon:</b> {it.action}</div>
                      {it.rationale && <div className="mt-1 text-[12px] text-muted-foreground"><b className="text-foreground">Why:</b> {it.rationale}</div>}
                      {it.proposed_message && (
                        <div className="mt-2">
                          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">What it will do</div>
                          <div className="mt-1 rounded-md border bg-background/40 px-3 py-2 text-[12px]">{it.proposed_message}</div>
                        </div>
                      )}
                      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {Object.entries(g).map(([kind, refs]) => (
                          <div key={kind}>
                            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{EV_TITLE[kind] ?? kind}</div>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              {refs.map((r, i) => (
                                <span key={i} className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">{r}</span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="flex w-[150px] shrink-0 flex-col gap-2">
                      <button onClick={() => decide(it.id, "approve")} disabled={pendingId === it.id} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50">✓ {pendingId === it.id ? "Working…" : it.channel === "email" ? "Approve & send" : "Approve"}</button>
                      <button onClick={() => decide(it.id, "edit")} disabled={pendingId === it.id} className="rounded-md border px-3 py-1.5 text-xs disabled:opacity-50">✎ Edit</button>
                      <button onClick={() => decide(it.id, "reject")} disabled={pendingId === it.id} className="rounded-md border px-3 py-1.5 text-xs text-rose-300 disabled:opacity-50">✕ Reject</button>
                      {it.risk === "high" && <div className="text-center text-[10px] text-muted-foreground">⏱ escalates in 4 h</div>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Queue table ─────────────────────────── */}
          {queue.length > 0 && (
            <div className="mt-6 rounded-xl border bg-card/60 p-4">
              <div className="mb-3 text-sm font-semibold">▦ Kuyruk ({queue.length} daha)</div>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium">Agent</th><th className="pb-2 pr-3 font-medium">Aksiyon</th>
                    <th className="pb-2 pr-3 font-medium">Risk</th><th className="pb-2 pr-3 font-medium">Consent</th>
                    <th className="pb-2 pr-3 font-medium">Policy</th><th className="pb-2 font-medium"></th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {queue.map((it) => (
                      <tr key={it.id}>
                        <td className="py-2.5 pr-3 font-medium">{it.agent_id}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{it.action}</td>
                        <td className="py-2.5 pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] ${RISK[it.risk] ?? ""}`}>{it.risk}</span></td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{it.consent_status || "—"}</td>
                        <td className="py-2.5 pr-3"><span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">{it.policy_result}</span></td>
                        <td className="py-2.5"><button onClick={() => confirmApprove(it)} disabled={pendingId === it.id} className="rounded-md border px-3 py-1 text-[11px] disabled:opacity-50">{pendingId === it.id ? "…" : "Onayla"}</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Outbox: onay → aksiyon izi (consent-gated) ─────────── */}
          {outbox && outbox.total > 0 && (
            <div className="mt-6 rounded-xl border bg-card/60 p-4" data-test="outbox">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">⇉ What actually ran</span>
                <span className="text-[11px] text-muted-foreground">Everything you approved, and what came of it. Outbound messages still need consent on file.</span>
                <div className="ml-auto flex gap-1.5">
                  {Object.entries(outbox.by_status).map(([s, n]) => (
                    <span key={s} className={`rounded-full border px-2 py-0.5 text-[10px] ${ACTION_STATUS[s] ?? "border-border text-muted-foreground"}`}>{STATUS_LABEL[s] ?? s}: {n}</span>
                  ))}
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium">Agent</th><th className="pb-2 pr-3 font-medium">Kind</th>
                    <th className="pb-2 pr-3 font-medium">Channel</th><th className="pb-2 pr-3 font-medium">Target</th>
                    <th className="pb-2 pr-3 font-medium">Status</th><th className="pb-2 pr-3 font-medium">Outcome</th>
                    <th className="pb-2 font-medium"></th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {outbox.items.map((a) => (
                      <tr key={a.id} data-test="outbox-row" data-status={a.status}>
                        <td className="py-2.5 pr-3 font-medium">{a.agent_id}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{ACTION_KIND[a.action_kind] ?? a.action_kind}</td>
                        <td className="py-2.5 pr-3 font-mono text-muted-foreground">{a.channel || "—"}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{a.target_company || "—"}{a.target_contact ? ` · ${a.target_contact}` : ""}</td>
                        <td className="py-2.5 pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] ${ACTION_STATUS[a.status] ?? "border-border"}`}>{STATUS_LABEL[a.status] ?? a.status}</span></td>
                        <td className="py-2.5 pr-3 text-[12px] text-muted-foreground">{a.reason}</td>
                        <td className="py-2.5">
                          {a.status === "failed" && a.action_kind === "message_send" && (
                            <button
                              data-test="outbox-retry"
                              onClick={() => retry(a.id)}
                              disabled={retryId === a.id}
                              className="rounded-md border px-3 py-1 text-[11px] disabled:opacity-50"
                            >
                              {retryId === a.id ? "…" : "Try again"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
