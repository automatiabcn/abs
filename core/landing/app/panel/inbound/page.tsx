/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Inbound Intelligence + Knowledge Base. POST /v1/inbound,
// POST /v1/knowledge/ask. Source-cited; outbound stays approval-gated.
"use client";

import { useState } from "react";

type Triage = {
  intent: string; draft: string; summary: string;
  citations: { kind: string; ref: string }[];
  confidence: number; requires_approval: boolean;
  approval?: { id: number; consent_status: string } | null;
};
type Answer = { answer: string; citations: { kind: string; ref: string }[]; confidence: number };

export default function InboundKnowledgePage() {
  const [msg, setMsg] = useState("");
  const [triage, setTriage] = useState<Triage | null>(null);
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);

  async function runInbound() {
    if (!msg.trim()) return;
    setBusy(true); setTriage(null);
    try {
      const r = await fetch("/v1/inbound", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: msg, channel: "web" }),
      });
      setTriage(await r.json());
    } finally { setBusy(false); }
  }
  async function ask() {
    if (!q.trim()) return;
    setBusy(true); setAns(null);
    try {
      const r = await fetch("/v1/knowledge/ask", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      setAns(await r.json());
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Inbound Intelligence + Knowledge Base</h1>
        <p className="mt-1 text-sm text-muted-foreground">Sort an incoming message and draft a reply with its sources · ask your knowledge base and get a cited answer</p>
      </div>

      <div className="mb-8 rounded-xl border bg-card/60 p-4">
        <div className="mb-2 text-sm font-semibold">⇄ Inbound Triage</div>
        <textarea value={msg} onChange={(e) => setMsg(e.target.value)} rows={2}
          placeholder="Paste a customer message… (e.g. 'How much is Premium PVC?')"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
        <button onClick={runInbound} disabled={busy} className="mt-2 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50">Sort and draft a reply</button>
        {triage && (
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-sky-500/40 px-2 py-0.5 font-mono text-[10px] text-sky-400">intent: {triage.intent}</span>
              {triage.requires_approval && <span className="rounded-full border border-amber-500/40 px-2 py-0.5 font-mono text-[10px] text-amber-400">approval{triage.approval ? ` #${triage.approval.id}` : ""}</span>}
              {triage.approval?.consent_status && <span className="rounded-full border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">consent: {triage.approval.consent_status}</span>}
            </div>
            {triage.draft && <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs">{triage.draft}</div>}
            {triage.citations?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">{triage.citations.map((c, i) => <span key={i} className="rounded-full border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">{c.kind}:{c.ref}</span>)}</div>
            )}
          </div>
        )}
      </div>

      <div className="rounded-xl border bg-card/60 p-4">
        <div className="mb-2 text-sm font-semibold">▥ Knowledge Base</div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question… (e.g. 'What services do you offer?')"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm" />
        <button onClick={ask} disabled={busy} className="mt-2 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50">Ask</button>
        {ans && (
          <div className="mt-3 space-y-2 text-sm">
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs">{ans.answer}</div>
            {ans.citations?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">{ans.citations.map((c, i) => <span key={i} className="rounded-full border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">{c.kind}:{c.ref}</span>)}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
