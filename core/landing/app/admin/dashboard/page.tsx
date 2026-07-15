/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Overview — license, beta, compliance, security and vault state from the
// single `/v1/admin/dashboard` endpoint.
//
// Redesign pass: English copy, the shared StatCard, and — the part that
// actually matters — state that reads as state. Every figure used to render in
// the same neutral grey, so a tampered audit chain and a healthy one looked
// identical until you read the caption under them. Compliance gaps, a failing
// security audit and a broken audit chain now carry the tone that says so.
"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CreditCard,
  Lock,
  ShieldCheck,
  Users,
} from "lucide-react";

import { PageHeader } from "@/components/ui/page-header";
import { StatCard, type StatTone } from "@/components/ui/stat-card";
import { Skeleton } from "@/components/ui/skeleton";

interface BillingSummary {
  licenses_total?: number;
  licenses_active?: number;
  tier_breakdown?: Record<string, number>;
}

interface DashboardPayload {
  billing?: BillingSummary;
  beta?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
  security?: Record<string, unknown>;
  vault?: Record<string, unknown>;
  generated_at?: number;
  cached?: boolean;
}

// The producers speak in status strings; the panel speaks in plain words and a
// tone. Keeping both maps next to each other keeps them from drifting.
const COMPLIANCE: Record<string, { label: string; tone: StatTone }> = {
  ok: { label: "Complete", tone: "good" },
  warn: { label: "Review", tone: "warn" },
  gap: { label: "Missing", tone: "bad" },
};

const SECURITY: Record<string, { label: string; tone: StatTone }> = {
  ok: { label: "Healthy", tone: "good" },
  warn: { label: "Review", tone: "warn" },
  danger: { label: "At risk", tone: "bad" },
};

export default function AdminDashboardPage() {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await fetch("/v1/admin/dashboard", {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const json = (await res.json()) as DashboardPayload;
        if (active) {
          setData(json);
          setLoading(false);
          setError(null);
        }
      } catch (exc) {
        if (active) {
          setError(exc instanceof Error ? exc.message : "unknown error");
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  // BUG (third-eye audit) — four of these cards read keys the producer tools
  // never emit, so every render showed 0 / — regardless of real state:
  //   beta.active_signups     → beta_metrics emits pending / approved
  //   compliance.soc2_score   → compliance_status emits overall_status + docs
  //   security.findings_count → security_audit emits overall_score + integrity
  //   vault.secrets_count     → vault audit stats() emits total_entries
  // Each card now reads a key the producer actually returns.
  const billing = data?.billing ?? {};
  const beta = (data?.beta ?? {}) as { pending?: number; approved?: number };
  const compliance = (data?.compliance ?? {}) as {
    overall_status?: "ok" | "warn" | "gap";
  };
  // security_audit.overall_score is a STATUS string (ok|warn|danger), not a
  // 0-100 number — render it as a labelled status, not "<n>/100".
  const security = (data?.security ?? {}) as {
    overall_score?: "ok" | "warn" | "danger";
  };
  const vault = (data?.vault ?? {}) as {
    total_entries?: number;
    // The backend (vault/audit_chain.py) emits a STATUS string "ok" |
    // "tampered", not a boolean — typing it as bool made the `=== false` tamper
    // check dead code, so the warning never surfaced on a genuinely tampered
    // chain.
    audit_chain_integrity?: "ok" | "tampered";
  };

  const betaCount = (beta.pending ?? 0) + (beta.approved ?? 0);
  const complianceState = compliance.overall_status
    ? COMPLIANCE[compliance.overall_status]
    : undefined;
  const securityState = security.overall_score
    ? SECURITY[security.overall_score]
    : undefined;
  const chainTampered = vault.audit_chain_integrity === "tampered";
  const tierTotal = Object.values(billing.tier_breakdown ?? {}).reduce(
    (a, b) => a + b,
    0,
  );

  return (
    <main
      data-page="admin-dashboard"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <PageHeader
        title="Overview"
        description="Licenses, beta accounts, compliance, security and the secret vault — five sources, one screen."
      />

      {error && (
        <div
          data-test="dashboard-error"
          className="mb-4 rounded border border-destructive bg-destructive-soft p-3 text-sm text-destructive"
        >
          Could not load the dashboard: {error}
        </div>
      )}

      <section
        data-test="dashboard-cards"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))
        ) : (
          <>
            <StatCard
              label="Active licenses"
              value={billing.licenses_active ?? 0}
              hint={`${billing.licenses_total ?? 0} on record`}
              icon={CreditCard}
            />
            <StatCard
              label="Beta accounts"
              value={betaCount}
              hint="Pending plus approved"
              icon={Users}
            />
            <StatCard
              label="Compliance"
              value={complianceState?.label ?? "—"}
              tone={complianceState?.tone ?? "neutral"}
              hint="DPA, privacy and retention documents"
              icon={CheckCircle2}
            />
            <StatCard
              label="Security"
              value={securityState?.label ?? "—"}
              tone={securityState?.tone ?? "neutral"}
              hint="TLS, key rotation and chain integrity"
              icon={AlertCircle}
            />
            <StatCard
              label="Vault audit"
              value={vault.total_entries ?? 0}
              tone={chainTampered ? "bad" : "neutral"}
              hint={
                chainTampered
                  ? "Chain integrity broken — investigate"
                  : "Entries in the audit chain"
              }
              icon={Lock}
            />
            <StatCard
              label="License tiers"
              value={tierTotal}
              hint={
                Object.keys(billing.tier_breakdown ?? {}).length
                  ? Object.entries(billing.tier_breakdown ?? {})
                      .map(([tier, n]) => `${tier}: ${n}`)
                      .join(" · ")
                  : "No tier breakdown yet"
              }
              icon={ShieldCheck}
            />
          </>
        )}
      </section>

      {data?.generated_at ? (
        <p className="mt-4 text-xs text-subtle">
          Updated {new Date(data.generated_at * 1000).toLocaleString("en-GB")}
          {data.cached ? " · cached" : " · live"}
        </p>
      ) : null}
    </main>
  );
}
