/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The /panel home screen.
//
// The three server-side payloads (`initialTools`, `initialQuota`,
// `initialCascade`) seed React Query as `initialData`, so the cards and the
// alert banner have real numbers on first paint instead of skeletons that
// swap in a moment later.
"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";

import { formatNumber } from "@/lib/format";
import type { CosmosWorld } from "@/components/CosmosGraph/buildGraph";
import {
  Activity,
  BarChart3,
  Layers,
  Package,
  ShieldCheck,
} from "lucide-react";

const CascadeAreaChart = dynamic(
  () => import("@/components/panel/charts/CascadeAreaChart"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-64 w-full" />,
  },
);
const CategoryBarList = dynamic(
  () => import("@/components/panel/charts/CategoryBarList"),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    ),
  },
);

const NeuralGraph = dynamic(
  () =>
    import("@/components/panel/NeuralGraph").then((m) => ({
      default: m.NeuralGraph,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="h-[460px] w-full animate-pulse rounded-md bg-muted/40" />
    ),
  },
);

import { StatCard } from "@/components/panel/StatCard";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  CascadeResponse,
  QuotaResponse,
  ToolsResponse,
} from "./types";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include", cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

interface PanelHomeClientProps {
  initialTools: ToolsResponse;
  initialQuota: QuotaResponse;
  initialCascade: CascadeResponse;
}

export default function PanelHomeClient({
  initialTools,
  initialQuota,
  initialCascade,
}: PanelHomeClientProps) {
  const tools = useQuery({
    queryKey: ["panel", "tools"],
    queryFn: () => fetchJson<ToolsResponse>("/v1/panel/tools"),
    initialData: initialTools,
    initialDataUpdatedAt: 0,
  });
  const quota = useQuery({
    queryKey: ["panel", "quota"],
    queryFn: () => fetchJson<QuotaResponse>("/v1/system/quota_status"),
    initialData: initialQuota,
    initialDataUpdatedAt: 0,
  });
  const cascade = useQuery({
    queryKey: ["panel", "cascade"],
    queryFn: () => fetchJson<CascadeResponse>("/v1/panel/cascade/recent"),
    initialData: initialCascade,
    initialDataUpdatedAt: 0,
  });

  const toolsTotal = tools.data?.total ?? 0;
  const cascadeCount = cascade.data?.count ?? 0;
  const providersActive = cascade.data?.providers_active ?? 0;
  const claudePct = quota.data?.claude_plus
    ? Math.round(quota.data.claude_plus.percent * 100)
    : 0;
  const claudeUsed = quota.data?.claude_plus?.used ?? 0;
  const claudeLimit = quota.data?.claude_plus?.limit ?? 0;

  const categoryBars = Object.entries(tools.data?.category_counts ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const cascadeSeries = (cascade.data?.timeseries ?? []).map((p) => ({
    date: p.ts,
    Calls: p.count,
  }));

  // The system map. Every node in it used to be hardcoded — seven providers,
  // four workflows, three RAG collections — on a server that might have one
  // provider and no documents, under a caption calling it live. It is built from
  // what the server reports now, and an empty server draws an empty map.
  const workflows = useQuery({
    queryKey: ["panel", "workflow-definitions"],
    queryFn: () =>
      fetchJson<{ workflows?: { id?: string; name?: string }[] }>(
        "/v1/workflows/definitions",
      ),
    retry: false,
  });
  const documents = useQuery({
    queryKey: ["panel", "rag-documents"],
    queryFn: () =>
      fetchJson<{ documents?: { id?: string; filename?: string }[] }>(
        "/v1/rag/documents",
      ),
    retry: false,
  });

  const world = useMemo<CosmosWorld>(
    () => ({
      providers: Object.keys(quota.data?.free_providers ?? {}),
      toolCategories: Object.entries(tools.data?.category_counts ?? {}).map(
        ([name, count]) => ({ name, count }),
      ),
      workflows: (workflows.data?.workflows ?? [])
        .map((w) => w.name || w.id || "")
        .filter(Boolean),
      documents: (documents.data?.documents ?? [])
        .map((d) => d.filename || d.id || "")
        .filter(Boolean),
    }),
    [quota.data, tools.data, workflows.data, documents.data],
  );

  return (
    <main
      data-page="panel-home"
      className="mx-auto w-full max-w-7xl px-6 py-10"
    >
      <motion.header
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="mb-8"
      >
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What your server has been doing: the questions it answered, who
          answered them, and how much of your quota is left.
        </p>
      </motion.header>

      <section
        data-test="panel-stats"
        className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <StatCard
          title="Tools"
          value={tools.isLoading ? "…" : toolsTotal}
          hint={
            tools.data?.category_counts
              ? `across ${Object.keys(tools.data.category_counts).length} categories`
              : "loading"
          }
          icon={Package}
          delay={0.0}
        />
        <StatCard
          title="Answers today"
          value={cascade.isLoading ? "…" : formatNumber(cascadeCount, "en")}
          hint={`${providersActive} providers answering`}
          icon={Activity}
          delay={0.05}
        />
        <StatCard
          title="Quota used"
          value={`${claudePct}%`}
          delta={
            claudeLimit > 0
              ? `${formatNumber(claudeUsed, "en")} / ${formatNumber(claudeLimit, "en")}`
              : undefined
          }
          deltaType={
            claudePct >= 95
              ? "decrease"
              : claudePct >= 80
                ? "neutral"
                : "increase"
          }
          icon={ShieldCheck}
          delay={0.1}
        />
        <StatCard
          title="Providers"
          value={providersActive}
          hint="ready to answer"
          icon={Layers}
          delay={0.15}
        />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.2 }}
          className="lg:col-span-2"
        >
          <Card className="bg-card/60 backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" />
                Answers over the last day
              </CardTitle>
              <CardDescription>
                Every question the server answered, by the hour.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {cascade.isLoading ? (
                <Skeleton className="h-64 w-full" />
              ) : cascadeSeries.length === 0 ? (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                  Nothing yet
                </div>
              ) : (
                <CascadeAreaChart data={cascadeSeries} />
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.25 }}
        >
          <Card className="h-full bg-card/60 backdrop-blur">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-primary" />
                What the tools do
              </CardTitle>
              <CardDescription>
                The eight biggest groups of tools this server can reach.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {tools.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-6 w-full" />
                  ))}
                </div>
              ) : categoryBars.length === 0 ? (
                <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
                  Nothing yet
                </div>
              ) : (
                <CategoryBarList data={categoryBars} />
              )}
            </CardContent>
          </Card>
        </motion.div>
      </section>

      <section className="mt-8">
        <Card className="bg-card/60 backdrop-blur">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              How it all connects
            </CardTitle>
            <CardDescription>
              The providers, tools, workflows and documents on this server — as it
              reports them. Nothing here is an example.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <NeuralGraph height={460} world={world} />
          </CardContent>
        </Card>
      </section>

      {(tools.isError || quota.isError || cascade.isError) && (
        <p
          role="alert"
          className="mt-6 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
        >
          Some of this could not be loaded. The server may be down — check that
          it is running, then reload.
        </p>
      )}
    </main>
  );
}
