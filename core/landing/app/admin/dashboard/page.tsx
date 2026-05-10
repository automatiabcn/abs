/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2B BUG-19/20/25/26 — `/admin/dashboard` canonical Genel Bakış.
// Aggregates billing + beta + compliance + security + vault from the
// existing `/v1/admin/dashboard` endpoint into a 5-card overview. The
// PanelSidebar "Genel Bakış" link now lands here directly (was a 308
// redirect to /admin/usage pre-rc7).
"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  CreditCard,
  Lock,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

function StatCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  description?: string;
  icon: typeof BarChart3;
}) {
  return (
    <Card className="bg-card/60">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon className="h-4 w-4 text-primary" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="font-mono text-2xl tracking-tight">{value}</div>
        {description ? (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

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
          setError(
            exc instanceof Error ? exc.message : "bilinmeyen hata"
          );
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  const billing = data?.billing ?? {};
  const beta = (data?.beta ?? {}) as { active_signups?: number };
  const compliance = (data?.compliance ?? {}) as { soc2_score?: number };
  const security = (data?.security ?? {}) as { findings_count?: number };
  const vault = (data?.vault ?? {}) as { secrets_count?: number };

  return (
    <main
      data-page="admin-dashboard"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <header className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <BarChart3 className="h-5 w-5 text-primary" />
          Genel Bakış
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Lisans, beta, uyumluluk, güvenlik ve secret vault durumu — beş kaynak
          tek panelde.
        </p>
      </header>

      {error && (
        <div
          data-test="dashboard-error"
          className="mb-4 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200"
        >
          Backend /v1/admin/dashboard hatası: {error}
        </div>
      )}

      <section
        data-test="dashboard-cards"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))
        ) : (
          <>
            <StatCard
              title="Aktif lisans"
              value={billing.licenses_active ?? 0}
              description={`Toplam ${billing.licenses_total ?? 0} kayıt`}
              icon={CreditCard}
            />
            <StatCard
              title="Beta kayıt"
              value={beta.active_signups ?? 0}
              description="Onay bekleyen + aktif beta hesapları"
              icon={Users}
            />
            <StatCard
              title="Uyumluluk skoru"
              value={
                compliance.soc2_score !== undefined
                  ? `${compliance.soc2_score}%`
                  : "—"
              }
              description="SOC2 audit chain durumu"
              icon={CheckCircle2}
            />
            <StatCard
              title="Güvenlik bulgu"
              value={security.findings_count ?? 0}
              description="Açık (high+critical) tarama bulgusu"
              icon={AlertCircle}
            />
            <StatCard
              title="Vault secret"
              value={vault.secrets_count ?? 0}
              description="Kayıtlı encrypted secret sayısı"
              icon={Lock}
            />
            <StatCard
              title="Tier dağılımı"
              value={Object.values(billing.tier_breakdown ?? {}).reduce(
                (a, b) => a + b,
                0,
              )}
              description={
                Object.keys(billing.tier_breakdown ?? {}).length
                  ? Object.entries(billing.tier_breakdown ?? {})
                      .map(([tier, n]) => `${tier}:${n}`)
                      .join(" · ")
                  : "Tier breakdown bekleniyor"
              }
              icon={ShieldCheck}
            />
          </>
        )}
      </section>

      {data?.generated_at ? (
        <p className="mt-4 text-xs text-muted-foreground">
          Üretildi {new Date(data.generated_at * 1000).toLocaleString("tr-TR")}
          {data.cached ? " · cache" : " · canlı"}
        </p>
      ) : null}
    </main>
  );
}
