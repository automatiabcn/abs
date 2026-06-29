/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Agent Registry screen. Wires GET /v1/agents (the 21-agent
// registry + runtime summary) into the panel, mirroring the design mockup.
"use client";

import { useEffect, useState } from "react";

type Agent = {
  id: string;
  name: string;
  purpose: string;
  icon: string;
  tools: string[];
  model: string;
  risk: "low" | "medium" | "high";
  requires_approval: boolean;
  success_metric: string;
};

type Category = { key: string; label: string; agents: Agent[] };

type Registry = {
  total: number;
  approval_gated: number;
  categories: Category[];
  structured_output: string;
};

const RISK_CLASS: Record<string, string> = {
  low: "border-emerald-500/40 text-emerald-400",
  medium: "border-amber-500/40 text-amber-400",
  high: "border-red-500/40 text-red-400",
};

function Chip({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] ${className}`}
    >
      {children}
    </span>
  );
}

export default function AgentRegistryPage() {
  const [data, setData] = useState<Registry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/v1/agents", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Registry) => setData(j))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Agent Registry</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Her agent kısıtlı tool + veri + model + risk + onay kuralı ile tanımlı ·
          structured output zorunlu
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">
          Yüklenemedi: {error}
        </div>
      )}

      {!data && !error && (
        <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />
      )}

      {data && (
        <>
          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Kayıtlı Agent" value={String(data.total)} hint="5 kategori · 120 MCP tool" />
            <Stat label="Onay-Kapılı" value={String(data.approval_gated)} hint="orta+ risk → Approval" />
            <Stat label="Structured Output" value="Zorunlu" hint="şema ile zorunlu · evidence_id + confidence" />
            <Stat label="Kategori" value={String(data.categories.length)} hint="discovery · intel · engage · ops" />
          </div>

          {data.categories.map((cat) => (
            <section key={cat.key} className="mb-8">
              <h2 className="mb-4 text-base font-semibold">{cat.label}</h2>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {cat.agents.map((a) => (
                  <div
                    key={a.id}
                    className="rounded-xl border bg-card/60 p-4 backdrop-blur transition hover:border-primary/50"
                  >
                    <div className="mb-2 flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/30 bg-primary/10 text-lg">
                        {a.icon}
                      </span>
                      <div>
                        <div className="text-sm font-semibold">{a.name}</div>
                        <div className="text-[11px] text-muted-foreground">{a.purpose}</div>
                      </div>
                    </div>
                    <div className="my-2 flex flex-wrap gap-1.5">
                      {a.tools.map((t) => (
                        <Chip key={t} className="border-border text-muted-foreground">
                          {t}
                        </Chip>
                      ))}
                    </div>
                    <div className="mt-2 flex items-center justify-between border-t pt-2 font-mono text-[10px] text-muted-foreground">
                      <span>{a.model}</span>
                      <Chip className={RISK_CLASS[a.risk] ?? "border-border"}>{a.risk} risk</Chip>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border bg-card/60 p-4 backdrop-blur">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>
    </div>
  );
}
