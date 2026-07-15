/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/pipelines` Quality Pipelines launcher. Lists all
// qual_* + race_* pipelines, exposes a Run form, polls
// /v1/panel/pipeline/recent for run history.
"use client";

import { formatDateTime } from "@/lib/format";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  GitMerge,
  Layers,
  PlayCircle,
  Sliders,
  Sparkles,
  Trophy,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface PipelineDef {
  id: string;
  label: string;
  family: "quality" | "race";
  description: string;
  chain: string[];
  icon: typeof Sparkles;
  tone: string;
}

const PIPELINES: PipelineDef[] = [
  {
    id: "qual_code",
    label: "qual_code",
    family: "quality",
    description: "Write code → verify → fix",
    chain: ["kimi+gpt20b", "codellama", "gptoss"],
    icon: Sparkles,
    tone: "emerald",
  },
  {
    id: "qual_tr",
    label: "qual_tr",
    family: "quality",
    description: "Write Turkish prose → check → polish",
    chain: ["qwen32b+gemini", "llama", "kimi2"],
    icon: Sparkles,
    tone: "amber",
  },
  {
    id: "qual_analysis",
    label: "qual_analysis",
    family: "quality",
    description: "Three viewpoints → one synthesis (deep analysis)",
    chain: ["gptoss+kimi2+gemini-pro", "synthesise"],
    icon: Sparkles,
    tone: "violet",
  },
  {
    id: "qual_translate",
    label: "qual_translate",
    family: "quality",
    description: "Translate → translate back → verify → fix",
    chain: ["qwen32b", "kimi", "gptoss"],
    icon: Sparkles,
    tone: "blue",
  },
  {
    id: "qual_code_human",
    label: "qual_code_human",
    family: "quality",
    description: "qual_code + humanize layer fingerprint",
    chain: ["qual_code", "humanize_score"],
    icon: Sparkles,
    tone: "pink",
  },
  {
    id: "qual_human",
    label: "qual_human",
    family: "quality",
    description: "General humanize layer — output reads closer to your own style",
    chain: ["qwen32b", "humanize"],
    icon: Sparkles,
    tone: "rose",
  },
  {
    id: "race",
    label: "race",
    family: "race",
    description: "Three models in parallel — the fastest answer wins",
    chain: ["gptoss", "kimi", "kimi2"],
    icon: Trophy,
    tone: "indigo",
  },
  {
    id: "race_code",
    label: "race_code",
    family: "race",
    description: "Code race: kimi vs gptoss20 vs cf-coder",
    chain: ["kimi", "gptoss20", "cf-coder"],
    icon: Trophy,
    tone: "emerald",
  },
  {
    id: "race_tr",
    label: "race_tr",
    family: "race",
    description: "Turkish prose race: qwen32b vs gemini vs kimi",
    chain: ["qwen32b", "gemini", "kimi"],
    icon: Trophy,
    tone: "amber",
  },
];

const TONE: Record<string, string> = {
  emerald: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
  amber: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  violet: "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30",
  blue: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
  pink: "bg-pink-500/15 text-pink-700 dark:text-pink-300 border-pink-500/30",
  rose: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30",
  indigo: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30",
};

interface RecentStep {
  role: string;
  model: string;
  latency_ms: number;
  ok: boolean;
}

interface RecentRun {
  ts: string;
  tool: string;
  elapsed_ms: number | null;
  // Real steps this run executed. Empty for rows written before step
  // recording — the row then shows "steps not recorded" rather than a
  // fabricated chain.
  steps: RecentStep[];
}

interface RecentResponse {
  count: number;
  pipeline_runs: RecentRun[];
}

interface RunStage {
  name: string;
  model: string;
  elapsed_ms: number;
  ok: boolean;
  error: string | null;
}

interface RunResponse {
  pipeline_id: string;
  completion: string;
  stages: RunStage[];
  providers: string[];
  verified: boolean | null;
  revisions: number | null;
  elapsed_ms: number;
  fallback: boolean;
  fallback_reason: string | null;
}

async function fetchRecent(): Promise<RecentResponse> {
  const res = await fetch("/v1/panel/pipeline/recent?limit=20", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function runPipeline(pipelineId: string, prompt: string): Promise<RunResponse> {
  // Runs the pipeline for real — the four qual_* chains through the QualResult
  // runner, race_* / humanize through the BasePipeline runner. The response
  // carries the steps it actually executed, not a placeholder.
  const res = await fetch("/v1/panel/pipeline/run", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline_id: pipelineId, prompt }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text.slice(0, 200) || `HTTP ${res.status}`);
  }
  return res.json() as Promise<RunResponse>;
}

export default function PipelinesPage() {
  const queryClient = useQueryClient();
  const [activePipeline, setActivePipeline] = useState<string>("qual_code");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recent = useQuery<RecentResponse>({
    queryKey: ["admin", "pipeline", "recent"],
    queryFn: fetchRecent,
    refetchInterval: 10000,
  });

  const run = useMutation({
    mutationFn: () => runPipeline(activePipeline, prompt),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      void queryClient.invalidateQueries({
        queryKey: ["admin", "pipeline", "recent"],
      });
    },
    onError: (exc) => {
      setError(exc instanceof Error ? exc.message : "unknown");
      setResult(null);
    },
  });

  const active = useMemo(
    () => PIPELINES.find((p) => p.id === activePipeline) ?? PIPELINES[0],
    [activePipeline],
  );

  return (
    <main
      data-page="admin-pipelines"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Sliders className="h-5 w-5 text-primary" />
          Quality Pipelines
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A chain of models, not one. Either write → verify → fix, or race
          several models and take the fastest answer.
        </p>
      </motion.header>

      <section
        data-test="pipelines-grid"
        className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {PIPELINES.map((p) => {
          const isActive = p.id === activePipeline;
          const Icon = p.icon;
          const tone = TONE[p.tone];
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setActivePipeline(p.id);
                setResult(null);
                setError(null);
              }}
              data-test="pipeline-card"
              data-pipeline-id={p.id}
              data-active={isActive}
              className={cn(
                "rounded-xl border bg-card/70 p-4 text-left transition-all",
                isActive
                  ? "border-primary/60 ring-2 ring-primary/30"
                  : "border-border hover:border-primary/30",
              )}
            >
              <div className="mb-2 flex items-center justify-between">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                    tone,
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {p.family}
                </span>
                <code className="font-mono text-[11px] text-muted-foreground">
                  {p.id}
                </code>
              </div>
              <h3 className="font-mono text-sm font-semibold text-foreground">
                {p.label}
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {p.description}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                {p.chain.map((step, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="rounded bg-muted/60 px-1.5 py-0.5 font-mono">
                      {step}
                    </span>
                    {i < p.chain.length - 1 && <GitMerge className="h-2.5 w-2.5" />}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </section>

      {/* ─── Run form ───────────────────────────────────── */}
      <Card className="mb-6 bg-card/70" data-test="pipeline-run-form">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <PlayCircle className="h-4 w-4 text-primary" />
            Run {active.label}
          </CardTitle>
          <CardDescription>{active.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={
              active.family === "quality"
                ? "What should the pipeline work on?"
                : "Which prompt should the models race on?"
            }
            className="w-full rounded-md border border-border bg-background p-3 text-sm outline-none focus:border-primary/50"
            data-test="pipeline-input"
          />
          <Button
            type="button"
            onClick={() => run.mutate()}
            disabled={run.isPending || !prompt.trim()}
            data-test="pipeline-run-button"
          >
            {run.isPending ? "Running…" : "Run"}
          </Button>
          {error && (
            <div
              role="alert"
              data-test="pipeline-error-tile"
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200"
            >
              <span>The run failed: {error}</span>
              {/* Match the chat panel's error UX: pair the
                  raw error string with a configure path + retry CTA so
                  the user knows where to go and how to recover. */}
              <div className="flex items-center gap-2">
                <a
                  href="/admin/settings"
                  data-test="pipeline-configure-cta"
                  className="rounded border border-rose-500/40 px-2 py-0.5 hover:bg-rose-500/20"
                >
                  Configure a provider
                </a>
                <button
                  type="button"
                  data-test="pipeline-retry-cta"
                  onClick={() => run.mutate()}
                  disabled={run.isPending || !prompt.trim()}
                  className="rounded border border-rose-500/40 px-2 py-0.5 hover:bg-rose-500/20 disabled:opacity-40"
                >
                  Try again
                </button>
              </div>
            </div>
          )}
          {result && (
            <div
              data-test="pipeline-output"
              className="space-y-3 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm"
            >
              {/* The steps this run actually executed, in order, with the model
                  and timing each took. This is what makes it a pipeline and not
                  a single call — so it is shown, not summarised away. */}
              {result.stages.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 text-[11px]">
                  {result.stages.map((s, i) => (
                    <span key={i} className="flex items-center gap-1">
                      <span
                        className={cn(
                          "flex items-center gap-1 rounded px-1.5 py-0.5 font-mono",
                          s.ok
                            ? "bg-muted/60 text-muted-foreground"
                            : "bg-rose-500/15 text-rose-600 dark:text-rose-300",
                        )}
                        title={s.error ?? undefined}
                      >
                        {s.name} · {s.model || "—"} ({s.elapsed_ms}ms)
                        {!s.ok && " ✕"}
                      </span>
                      {i < result.stages.length - 1 && (
                        <GitMerge className="h-2.5 w-2.5 text-muted-foreground" />
                      )}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                {result.verified != null && (
                  <Badge
                    variant="outline"
                    className={cn(
                      "font-mono",
                      result.verified
                        ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-300"
                        : "border-amber-500/40 text-amber-700 dark:text-amber-300",
                    )}
                  >
                    {result.verified ? "verified" : "not verified"}
                  </Badge>
                )}
                {result.revisions != null && result.revisions > 0 && (
                  <span>{result.revisions} revision{result.revisions === 1 ? "" : "s"}</span>
                )}
                <span>{result.elapsed_ms}ms total</span>
                {result.fallback && (
                  <span className="text-amber-600 dark:text-amber-400">
                    fell back to a single model
                    {result.fallback_reason ? ` — ${result.fallback_reason}` : ""}
                  </span>
                )}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
                {result.completion}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ─── Recent runs ────────────────────────────────── */}
      <Card className="bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers className="h-4 w-4 text-primary" />
            Recent runs
          </CardTitle>
          <CardDescription>
            The last 20 pipeline runs, refreshed every 10 seconds.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recent.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (recent.data?.pipeline_runs ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No pipeline runs yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {(recent.data?.pipeline_runs ?? []).map((r, i) => (
                <li
                  key={`${r.ts}-${i}`}
                  data-test="pipeline-run-row"
                  className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-background/40 px-3 py-2 text-xs"
                >
                  <Badge variant="outline" className="border-primary/30 font-mono">
                    {r.tool}
                  </Badge>
                  <span className="text-muted-foreground">
                    {formatDateTime(new Date(r.ts), "en")}
                  </span>
                  {r.elapsed_ms != null && (
                    <span className="font-mono text-muted-foreground">
                      {r.elapsed_ms}ms
                    </span>
                  )}
                  <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                    {r.steps.length === 0 ? (
                      <span className="italic">steps not recorded</span>
                    ) : (
                      r.steps.map((s, j) => (
                        <span
                          key={j}
                          className={cn(
                            "flex items-center gap-1 rounded px-1.5 py-0.5 font-mono",
                            s.ok
                              ? "bg-muted/60"
                              : "bg-rose-500/15 text-rose-600 dark:text-rose-300",
                          )}
                        >
                          {s.role} · {s.model || "—"} ({s.latency_ms}ms)
                          {!s.ok && " ✕"}
                        </span>
                      ))
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
