/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Agentic Growth — Growth Dashboard. Mirrors mockup 01_dashboard.html: four
// scorecards, the live agent-activity feed, buying-signal fusion, the
// account-priority table, and the AEO / campaign / inbound / CRM / connector /
// model-gateway summary widgets. Wires GET /v1/dashboard.
"use client";

import { useEffect, useState } from "react";

type Activity = {
  agent_id: string;
  summary: string;
  risk: string;
  requires_approval: boolean;
  created_at: string | null;
};
type Lead = {
  id: number;
  company_name: string;
  sector: string;
  intent: string;
  score: number;
  consent_status: string;
  recommended_action: string;
};
type Signal = { icon: string; label: string; company: string };

type Dashboard = {
  scorecards: {
    growth_score: number;
    hot_accounts: number;
    pending_approvals: number;
    high_risk_approvals: number;
    active_agents: number;
    total_agents: number;
  };
  activity: Activity[];
  buying_signals: { items: Signal[]; signal_types: number };
  account_priority: Lead[];
  aeo: { visibility_pct: number | null; down_categories: number; categories_total: number };
  campaign: { attributed_revenue: number | null; currency: string; top_channel: string; period: string };
  inbound_today: number;
  crm_health: { health_pct: number | null; fix_suggestions: number };
  connectors: { connected: number; catalog: number; health: number };
  model_gateway: { cost: number; currency: string; models: number; mode: string };
};

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-xl border bg-card/60 p-4 backdrop-blur ${className}`}>{children}</div>;
}

function Score({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: string }) {
  return (
    <Card>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${accent ?? ""}`}>{value}</div>
      {hint && <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>}
    </Card>
  );
}

const INTENT_CHIP: Record<string, string> = {
  high: "border-emerald-500/40 text-emerald-300",
  medium: "border-amber-500/40 text-amber-300",
  watching: "border-border text-muted-foreground",
};
const CONSENT_LABEL: Record<string, string> = {
  opted_in: "Opted in", pending: "Pending", opted_out: "Opted out",
  "opt-in": "Opted in", "opt-out": "Opted out", partial: "Partial",
};

function trTime(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins} min ago`;
  return `${Math.round(mins / 60)} h ago`;
}

export default function GrowthDashboardPage() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/v1/dashboard", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Dashboard) => setD(j))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Growth Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What your agents did, and which accounts to work next
          </p>
        </div>
        {d && (
          <span className="rounded-full border border-emerald-500/40 px-3 py-1 text-[11px] text-emerald-300">
            ● All systems healthy · {d.scorecards.active_agents} agents running
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm text-red-400">
          Could not load the dashboard: {error}
        </div>
      )}
      {!d && !error && <div className="h-64 w-full animate-pulse rounded-md bg-muted/40" />}

      {d && (
        <>
          {/* ── Scorecards ─────────────────────────── */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Score label="Growth Score" value={`${d.scorecards.growth_score}/100`} hint="average lead score" accent="text-emerald-300" />
            <Score label="Hot Accounts" value={String(d.scorecards.hot_accounts)} hint="leads showing high intent" />
            <Score label="Waiting for Approval" value={String(d.scorecards.pending_approvals)} hint={`${d.scorecards.high_risk_approvals} high-risk · needs a person`} accent="text-amber-300" />
            <Score label="Agents Running" value={`${d.scorecards.active_agents}/${d.scorecards.total_agents}`} hint="seen in recent activity" />
          </div>

          {/* ── Activity feed + Buying signals ─────── */}
          <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <div className="mb-3 text-sm font-semibold">⚡ Live Agent Activity</div>
              <div className="divide-y divide-border">
                {d.activity.length === 0 && <div className="py-3 text-sm text-muted-foreground">No activity yet.</div>}
                {d.activity.slice(0, 8).map((a, i) => (
                  <div key={i} className="flex items-start gap-3 py-2.5">
                    <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded bg-muted/40 text-xs">⚙</span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px]">
                        <span className="font-medium text-primary">{a.agent_id}</span> — {a.summary}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground">{trTime(a.created_at)}</div>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] ${a.requires_approval ? "border-amber-500/40 text-amber-300" : "border-emerald-500/40 text-emerald-300"}`}>
                      {a.requires_approval ? "needs approval" : "done"}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <div className="mb-1 text-sm font-semibold">◈ Buying Signals</div>
              <div className="mb-3 text-[11px] text-muted-foreground">
                Watching {d.buying_signals.signal_types} kinds of signal
              </div>
              <div className="space-y-2">
                {d.buying_signals.items.length === 0 && <div className="text-sm text-muted-foreground">No signals yet.</div>}
                {d.buying_signals.items.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-lg border bg-background/40 px-3 py-2">
                    <span className="text-base">{s.icon}</span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px]">{s.label}</div>
                      <div className="truncate text-[11px] text-muted-foreground">{s.company}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* ── Account Priority table ─────────────── */}
          <Card className="mb-6">
            <div className="mb-3 text-sm font-semibold">◷ Accounts to Work Next</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium">Company</th>
                    <th className="pb-2 pr-3 font-medium">Industry</th>
                    <th className="pb-2 pr-3 font-medium">Score</th>
                    <th className="pb-2 pr-3 font-medium">Intent</th>
                    <th className="pb-2 pr-3 font-medium">Consent</th>
                    <th className="pb-2 font-medium">Suggested next step</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {d.account_priority.length === 0 && (
                    <tr><td colSpan={6} className="py-3 text-muted-foreground">No leads yet.</td></tr>
                  )}
                  {d.account_priority.map((ln) => (
                    <tr key={ln.id}>
                      <td className="py-2.5 pr-3 font-medium">{ln.company_name}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{ln.sector || "—"}</td>
                      <td className="py-2.5 pr-3 font-mono">{ln.score.toFixed(2)}</td>
                      <td className="py-2.5 pr-3">
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] ${INTENT_CHIP[ln.intent] ?? INTENT_CHIP.watching}`}>{ln.intent}</span>
                      </td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{CONSENT_LABEL[ln.consent_status] ?? (ln.consent_status || "—")}</td>
                      <td className="py-2.5 text-muted-foreground">{ln.recommended_action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* ── Summary widgets ────────────────────── */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
            <Score
              label="Search Visibility"
              value={d.aeo.visibility_pct != null ? `${d.aeo.visibility_pct}%` : "—"}
              hint={`down in ${d.aeo.down_categories} of ${d.aeo.categories_total} categories`}
            />
            <Score
              label="Campaign → Revenue"
              value={d.campaign.attributed_revenue != null
                ? `${d.campaign.currency}${(d.campaign.attributed_revenue / 1_000_000).toFixed(2)}M`
                : "—"}
              hint={d.campaign.top_channel ? `${d.campaign.top_channel} · ${d.campaign.period}` : "revenue attributed to campaigns"}
              accent="text-emerald-300"
            />
            <Score label="Inbound (today)" value={String(d.inbound_today)} hint="requests triaged" />
            <Score
              label="CRM Data Health"
              value={d.crm_health.health_pct != null ? `${d.crm_health.health_pct}%` : "—"}
              hint={`${d.crm_health.fix_suggestions} fixes suggested`}
            />
            <Score
              label="Connectors"
              value={`${d.connectors.connected}/${d.connectors.catalog}`}
              hint={d.connectors.health ? `${d.connectors.health}% average health` : "connected / available"}
            />
            <Score
              label="Model Gateway"
              value={`${d.model_gateway.currency}${d.model_gateway.cost}`}
              hint={`${d.model_gateway.mode} · ${d.model_gateway.models} models`}
              accent="text-emerald-300"
            />
          </div>
        </>
      )}
    </div>
  );
}
