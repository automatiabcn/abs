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

import { useMemo, useState } from "react";
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

// One real agent execution, as the dashboard reports it — the raw material for
// the "what the server did" feed.
type ActivityEvidence = { kind: string; ref: string; excerpt: string };
type ActivityItem = {
  id: number;
  agent_id: string;
  task?: string;
  summary: string;
  risk?: string;
  requires_approval?: boolean;
  provider?: string;
  elapsed_ms?: number;
  created_at?: string | null;
  evidence?: ActivityEvidence[];
};

const EVIDENCE_KIND: Record<string, string> = {
  rag: "border-violet-500/40 text-violet-700 dark:text-violet-300",
  graph: "border-primary/50 text-primary",
  signal: "border-amber-500/40 text-amber-700 dark:text-amber-300",
};

const ACTIVITY_RISK: Record<string, string> = {
  low: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
  medium: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  high: "border-red-500/40 text-red-700 dark:text-red-300",
};

function prettyAgent(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function relTime(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
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
  // Real agent runs for the "what the server did" feed (the page already
  // promises this — "who ran what" — but never rendered the list).
  const dashboard = useQuery({
    queryKey: ["panel", "dashboard-activity"],
    queryFn: () => fetchJson<{ activity?: ActivityItem[] }>("/v1/dashboard"),
    retry: false,
  });
  const activity = dashboard.data?.activity ?? [];
  const [openRun, setOpenRun] = useState<number | null>(null);

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
              Recent activity
            </CardTitle>
            <CardDescription>
              What the server actually did — the newest agent runs, in plain
              language. Each row is a real run, not an example.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {dashboard.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : activity.length === 0 ? (
              <div className="flex h-24 items-center justify-center text-center text-sm text-muted-foreground">
                Nothing yet — as the server answers questions and runs agents,
                each action shows up here.
              </div>
            ) : (
              <ul className="divide-y divide-border" data-test="home-activity">
                {activity.map((a) => {
                  const open = openRun === a.id;
                  const ev = a.evidence ?? [];
                  return (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => setOpenRun(open ? null : a.id)}
                        aria-expanded={open}
                        className="flex w-full items-start justify-between gap-3 py-2.5 text-left transition hover:opacity-80"
                        data-test="home-activity-row"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 text-sm font-medium">
                            <span className={`text-[10px] text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
                            {prettyAgent(a.agent_id)}
                          </div>
                          <div className={`text-xs text-muted-foreground ${open ? "" : "truncate"}`}>{a.summary || "—"}</div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2 text-[11px]">
                          {a.requires_approval && (
                            <span className="rounded-full border border-rose-500/40 px-1.5 py-0.5 text-rose-700 dark:text-rose-300">needs approval</span>
                          )}
                          {a.risk && (
                            <span className={`rounded-full border px-1.5 py-0.5 font-mono ${ACTIVITY_RISK[a.risk] ?? "border-border text-muted-foreground"}`}>{a.risk}</span>
                          )}
                          {a.provider && <span className="hidden font-mono text-muted-foreground sm:inline">{a.provider}</span>}
                          <span className="whitespace-nowrap text-muted-foreground">{relTime(a.created_at)}</span>
                        </div>
                      </button>
                      {open && (
                        <div className="mb-2 space-y-2 rounded-lg border border-border bg-muted/30 p-3 text-xs">
                          {a.task && (
                            <div>
                              <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">Asked to</div>
                              <div className="text-foreground">{a.task}</div>
                            </div>
                          )}
                          <div>
                            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                              What it pulled {ev.length > 0 && `· ${ev.length} source${ev.length === 1 ? "" : "s"}`}
                            </div>
                            {ev.length === 0 ? (
                              <div className="text-muted-foreground">No sources recorded for this run — it answered from the model alone.</div>
                            ) : (
                              <ul className="space-y-1.5">
                                {ev.map((e, i) => (
                                  <li key={i} className="flex gap-2">
                                    <span className={`mt-0.5 h-fit shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] uppercase ${EVIDENCE_KIND[e.kind] ?? "border-border text-muted-foreground"}`}>{e.kind}</span>
                                    <span className="min-w-0">
                                      {e.ref && <span className="font-mono text-[10px] text-muted-foreground">{e.ref}</span>}
                                      {e.excerpt && <span className="block text-foreground">{e.excerpt}</span>}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
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
