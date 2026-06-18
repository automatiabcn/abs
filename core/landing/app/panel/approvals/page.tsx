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
  queued: "border-sky-500/40 text-sky-300",
  blocked: "border-rose-500/40 text-rose-300",
  failed: "border-amber-500/40 text-amber-300",
};
const STATUS_LABEL: Record<string, string> = {
  executed: "✓ uygulandı", queued: "✓ kuyruğa alındı", blocked: "⛔ engellendi",
  failed: "⚠ hata", rejected: "✕ reddedildi",
};
function trTime(iso: string | null): string {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} dk önce` : `${Math.round(m / 60)} sa önce`;
}
function evGroups(ev: Evidence[]) {
  const g: Record<string, string[]> = {};
  for (const e of ev || []) (g[e.kind] ??= []).push(e.ref);
  return g;
}
const EV_TITLE: Record<string, string> = {
  rag: "KANIT · RAG", graph: "KANIT · GRAPH", consent: "CONSENT EVIDENCE", policy: "POLICY SONUCU",
};

export default function ApprovalCenterPage() {
  const [d, setD] = useState<Data | null>(null);
  const [outbox, setOutbox] = useState<Outbox | null>(null);
  const [result, setResult] = useState<{ status: string; reason: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

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
    const r = await fetch(`/v1/approvals/${id}/decide`, {
      method: "POST", credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    const j = await r.json().catch(() => null);
    if (j?.action) setResult({ status: j.action.status, reason: j.action.reason });
    else if (decision === "reject") setResult({ status: "rejected", reason: "aksiyon tetiklenmedi" });
    load();
  }

  const detailed = (d?.items ?? []).filter((i) => i.rationale);
  const queue = (d?.items ?? []).filter((i) => !i.rationale);
  const t = d?.tier_stats;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Approval Center</h1>
          <p className="mt-1 text-[12px] text-muted-foreground">agent önerileri insan onayına düşer · gerekçe + kanıt + risk + consent + policy görünür</p>
        </div>
        {d && (
          <div className="flex gap-2 text-[11px]">
            <span className="rounded-full border border-amber-500/40 px-3 py-1 text-amber-300">{d.pending_total} bekliyor</span>
            <span className="rounded-full border border-rose-500/40 px-3 py-1 text-rose-300">{d.by_risk.high ?? 0} yüksek-risk</span>
          </div>
        )}
      </div>
      {err && <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">Yüklenemedi: {err}</div>}
      {result && (
        <div data-test="action-result" className={`mb-4 flex items-center justify-between rounded-lg border px-4 py-2.5 text-sm ${result.status === "blocked" ? "border-rose-500/40 bg-rose-500/5 text-rose-200" : result.status === "failed" ? "border-amber-500/40 bg-amber-500/5 text-amber-200" : result.status === "rejected" ? "border-border bg-muted/20 text-muted-foreground" : "border-emerald-500/40 bg-emerald-500/5 text-emerald-200"}`}>
          <span><b>Aksiyon:</b> {STATUS_LABEL[result.status] ?? result.status} · {result.reason}</span>
          <button onClick={() => setResult(null)} className="text-xs opacity-70 hover:opacity-100">kapat</button>
        </div>
      )}
      {!d && !err && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {d && (
        <>
          {/* ── Tier scorecards ─────────────────────── */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              ["Düşük (otomatik)", String(t?.low_auto ?? 0), "iç rapor · CRM okuma · brief"],
              ["Orta (insan)", String(t?.medium_pending ?? 0), "email taslağı · CRM update"],
              ["Yüksek (onay+audit)", String(t?.high_pending ?? 0), "outbound · WhatsApp"],
              ["Onay kabul oranı", t?.accept_rate != null ? `%${t.accept_rate}` : "—", "risk-bazlı akıllı eşik · batch"],
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
            {detailed.length === 0 && <div className="text-sm text-muted-foreground">Detaylı bekleyen onay yok.</div>}
            {detailed.map((it) => {
              const g = evGroups(it.evidence);
              return (
                <div key={it.id} className="rounded-xl border bg-card/60 p-4">
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
                      {it.rationale && <div className="mt-1 text-[12px] text-muted-foreground"><b className="text-foreground">Agent gerekçesi:</b> {it.rationale}</div>}
                      {it.proposed_message && (
                        <div className="mt-2">
                          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Önerilen mesaj</div>
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
                      <button onClick={() => decide(it.id, "approve")} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground">✓ {it.channel === "email" ? "Onayla & Gönder" : "Onayla"}</button>
                      <button onClick={() => decide(it.id, "edit")} className="rounded-md border px-3 py-1.5 text-xs">✎ Düzenle</button>
                      <button onClick={() => decide(it.id, "reject")} className="rounded-md border px-3 py-1.5 text-xs text-rose-300">✕ Reddet</button>
                      {it.risk === "high" && <div className="text-center text-[10px] text-muted-foreground">⏱ 4s sonra escalate</div>}
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
                        <td className="py-2.5"><button onClick={() => decide(it.id, "approve")} className="rounded-md border px-3 py-1 text-[11px]">İncele</button></td>
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
                <span className="text-sm font-semibold">⇉ Aksiyon Outbox</span>
                <span className="text-[11px] text-muted-foreground">onaydan sonra çalışan aksiyonlar · Consent Ledger ile geçitlenir</span>
                <div className="ml-auto flex gap-1.5">
                  {Object.entries(outbox.by_status).map(([s, n]) => (
                    <span key={s} className={`rounded-full border px-2 py-0.5 text-[10px] ${ACTION_STATUS[s] ?? "border-border text-muted-foreground"}`}>{STATUS_LABEL[s] ?? s}: {n}</span>
                  ))}
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium">Agent</th><th className="pb-2 pr-3 font-medium">Tür</th>
                    <th className="pb-2 pr-3 font-medium">Kanal</th><th className="pb-2 pr-3 font-medium">Hedef</th>
                    <th className="pb-2 pr-3 font-medium">Durum</th><th className="pb-2 font-medium">Gerekçe</th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {outbox.items.map((a) => (
                      <tr key={a.id}>
                        <td className="py-2.5 pr-3 font-medium">{a.agent_id}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{a.action_kind === "message_send" ? "mesaj" : "iç aksiyon"}</td>
                        <td className="py-2.5 pr-3 font-mono text-muted-foreground">{a.channel || "—"}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{a.target_company || "—"}{a.target_contact ? ` · ${a.target_contact}` : ""}</td>
                        <td className="py-2.5 pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] ${ACTION_STATUS[a.status] ?? "border-border"}`}>{STATUS_LABEL[a.status] ?? a.status}</span></td>
                        <td className="py-2.5 text-[12px] text-muted-foreground">{a.reason}</td>
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
