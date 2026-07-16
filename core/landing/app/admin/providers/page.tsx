/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// `/admin/providers` cascade chain visualisation. Polls
// /v1/cascade/providers every 5s, shows 6 provider cards with status
// chips, mock-mode toggle, last 10 cascade calls, and a `Test now`
// button that fires a `/v1/cascade/run` for live trace.
"use client";

import { formatDate } from "@/lib/format";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Layers,
  PlayCircle,
  Settings2,
  XCircle,
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
import ProviderConfigModal, {
  type ProviderConfigEntry,
} from "@/components/admin/ProviderConfigModal";
import { cn } from "@/lib/utils";

interface ProvidersStatusResponse {
  providers: ProviderConfigEntry[];
}

async function fetchProvidersStatus(): Promise<ProvidersStatusResponse> {
  const res = await fetch("/v1/admin/providers/status", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

interface ProvidersResponse {
  active: string[];
  missing: string[];
  configured_count: number;
  total: number;
  anthropic_mock_mode: string;
}

interface CascadeRun {
  ts: number;
  prompt: string;
  provider: string;
  fallbackChain: string[];
  tokensUsed: number;
  mock: boolean;
  ok: boolean;
  detail?: string;
}

const CASCADE_ORDER = [
  "anthropic-mock",
  "groq",
  "cerebras",
  "cloudflare",
  "gemini",
  "cohere",
  "anthropic",
] as const;

const PROVIDER_LABELS: Record<string, { label: string; tone: string }> = {
  "anthropic-mock": { label: "Anthropic Mock", tone: "amber" },
  groq: { label: "Groq", tone: "indigo" },
  cerebras: { label: "Cerebras", tone: "violet" },
  cloudflare: { label: "Cloudflare", tone: "orange" },
  gemini: { label: "Gemini", tone: "blue" },
  cohere: { label: "Cohere", tone: "pink" },
  anthropic: { label: "Anthropic", tone: "emerald" },
};

const TONE_BG: Record<string, string> = {
  amber: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  indigo: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30",
  violet: "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30",
  orange: "bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30",
  blue: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
  pink: "bg-pink-500/15 text-pink-700 dark:text-pink-300 border-pink-500/30",
  emerald: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
};

async function fetchProviders(): Promise<ProvidersResponse> {
  const res = await fetch("/v1/cascade/providers", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function runCascade(prompt: string) {
  const res = await fetch("/v1/cascade/run", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, max_tokens: 128 }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text.slice(0, 200) || `HTTP ${res.status}`);
  }
  return res.json() as Promise<{
    completion: string;
    provider: string;
    fallback_chain: string[];
    tokens_used: number;
    mock: boolean;
  }>;
}

function StatusChip({
  configured,
  mock,
}: {
  configured: boolean;
  mock?: boolean;
}) {
  if (mock) {
    return (
      <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
        Mock on
      </Badge>
    );
  }
  return configured ? (
    <Badge
      variant="outline"
      className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300"
    >
      <CheckCircle2 className="mr-1 h-3 w-3" />
      Ready
    </Badge>
  ) : (
    <Badge variant="outline" className="border-rose-500/40 text-rose-700 dark:text-rose-300">
      <XCircle className="mr-1 h-3 w-3" />
      No key
    </Badge>
  );
}

export default function ProvidersPage() {
  const queryClient = useQueryClient();
  const [history, setHistory] = useState<CascadeRun[]>([]);
  const [animatingProvider, setAnimatingProvider] = useState<string | null>(
    null,
  );
  // Selected provider drives the config modal.
  const [activeConfig, setActiveConfig] = useState<ProviderConfigEntry | null>(
    null,
  );

  const providers = useQuery<ProvidersResponse>({
    queryKey: ["admin", "providers"],
    queryFn: fetchProviders,
    refetchInterval: 5000,
  });

  // Pull the configured-or-not flag for each provider
  // so the modal can render the masked-key state without exposing the
  // raw value. Cached for 30s; the test button itself does NOT poll.
  const status = useQuery<ProvidersStatusResponse>({
    queryKey: ["admin", "providers", "status"],
    queryFn: fetchProvidersStatus,
    staleTime: 30_000,
  });

  const test = useMutation({
    mutationFn: () => runCascade("Health probe — ping cascade router"),
    onSuccess: (data) => {
      const run: CascadeRun = {
        ts: Date.now(),
        prompt: "Health probe",
        provider: data.provider,
        fallbackChain: data.fallback_chain,
        tokensUsed: data.tokens_used,
        mock: data.mock,
        ok: true,
      };
      setHistory((prev) => [run, ...prev].slice(0, 10));
      setAnimatingProvider(data.provider);
      window.setTimeout(() => setAnimatingProvider(null), 1500);
      void queryClient.invalidateQueries({ queryKey: ["admin", "providers"] });
    },
    onError: (exc) => {
      setHistory((prev) =>
        [
          {
            ts: Date.now(),
            prompt: "Health probe",
            provider: "—",
            fallbackChain: [],
            tokensUsed: 0,
            mock: false,
            ok: false,
            detail: exc instanceof Error ? exc.message : "unknown",
          },
          ...prev,
        ].slice(0, 10),
      );
    },
  });

  const cards = useMemo(() => {
    const active = new Set(providers.data?.active ?? []);
    const mockMode = providers.data?.anthropic_mock_mode ?? "off";
    return CASCADE_ORDER.map((name) => ({
      name,
      configured:
        name === "anthropic-mock" ? mockMode !== "off" : active.has(name),
      mock: name === "anthropic-mock",
    }));
  }, [providers.data]);

  return (
    <div
      data-page="admin-providers"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6 flex items-start justify-between"
      >
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Layers className="h-5 w-5 text-primary" />
            Providers
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your providers are tried in order. If one is down or out of quota,
            the next one takes the call.
          </p>
        </div>
        <Button
          type="button"
          onClick={() => test.mutate()}
          disabled={test.isPending}
          data-test="cascade-test-now"
        >
          <PlayCircle className="mr-2 h-4 w-4" />
          {test.isPending ? "Testing…" : "Send a test call"}
        </Button>
      </motion.header>

      {/* ─── Visual cascade chain ───────────────────────── */}
      <Card className="mb-6 bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Fallback order</CardTitle>
          <CardDescription>
            Tried left to right. Send a test call and the provider that answers
            lights up.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            {cards.map((c, i) => {
              const tone = TONE_BG[PROVIDER_LABELS[c.name]?.tone ?? "indigo"];
              const isAnimating = animatingProvider === c.name;
              return (
                <div key={c.name} className="flex items-center gap-2">
                  <motion.div
                    animate={
                      isAnimating
                        ? { scale: [1, 1.06, 1], opacity: [1, 0.8, 1] }
                        : {}
                    }
                    transition={{ duration: 0.6, repeat: isAnimating ? 1 : 0 }}
                    data-test="cascade-node"
                    data-provider={c.name}
                    data-active={c.configured}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs font-medium",
                      tone,
                      !c.configured && "opacity-40",
                      isAnimating && "ring-2 ring-primary/60",
                    )}
                  >
                    {PROVIDER_LABELS[c.name]?.label ?? c.name}
                  </motion.div>
                  {i < cards.length - 1 && (
                    <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  )}
                </div>
              );
            })}
          </div>
          {providers.data && (
            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span>
                <strong className="text-foreground">
                  {providers.data.configured_count}
                </strong>{" "}
                of {providers.data.total} providers ready
              </span>
              <Badge
                variant="outline"
                data-test="mock-mode-badge"
                className={cn(
                  providers.data.anthropic_mock_mode !== "off"
                    ? "border-amber-500/40 text-amber-700 dark:text-amber-300"
                    : "border-border",
                )}
              >
                anthropic_mock_mode = {providers.data.anthropic_mock_mode}
              </Badge>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ─── 6 provider cards ───────────────────────────── */}
      <section
        data-test="provider-grid"
        className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {providers.isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))
          : cards.map((c) => {
              const meta = PROVIDER_LABELS[c.name];
              const tone = TONE_BG[meta?.tone ?? "indigo"];
              return (
                <Card
                  key={c.name}
                  data-test="provider-card"
                  data-provider={c.name}
                  className={cn(
                    "bg-card/70 transition-colors",
                    !c.configured && "opacity-70",
                  )}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">
                        {meta?.label ?? c.name}
                      </CardTitle>
                      <StatusChip configured={c.configured} mock={c.mock} />
                    </div>
                    <CardDescription className="font-mono text-xs">
                      {c.name}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    <div className="flex items-center justify-between text-muted-foreground">
                      <span>Position</span>
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px]", tone)}>
                        {CASCADE_ORDER.indexOf(c.name as (typeof CASCADE_ORDER)[number]) + 1}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-muted-foreground">
                      <span>Mode</span>
                      <span>{c.mock ? "deterministic" : "live"}</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2 w-full"
                      data-test="provider-configure"
                      onClick={() => {
                        // Anthropic-mock has no real
                        // key to test against; clicking it just opens the
                        // settings link path inside the modal.
                        const fromStatus =
                          status.data?.providers.find(
                            (p) => p.id === c.name,
                          ) ?? null;
                        setActiveConfig(
                          fromStatus ?? {
                            id: c.name,
                            label: meta?.label ?? c.name,
                            configured: c.configured,
                          },
                        );
                      }}
                    >
                      <Settings2 className="mr-2 h-3 w-3" />
                      Configure
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
      </section>

      {/* ─── Recent calls timeline ──────────────────────── */}
      <Card className="bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-primary" />
            Recent calls
          </CardTitle>
          <CardDescription>
            The last 10 test calls, and which provider answered each one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No calls yet. Start with <kbd>Send a test call</kbd>.
            </p>
          ) : (
            <ul className="space-y-2">
              {history.map((h, i) => (
                <li
                  key={`${h.ts}-${i}`}
                  data-test="cascade-call"
                  className={cn(
                    "rounded-md border px-3 py-2 text-xs",
                    h.ok
                      ? "border-border bg-background/40"
                      : "border-rose-500/30 bg-rose-500/10",
                  )}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <Boxes className="h-3 w-3 text-muted-foreground" />
                    <span className="font-mono text-muted-foreground">
                      {formatDate(new Date(h.ts), "en", { timeStyle: "short" })}
                    </span>
                    {h.ok ? (
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-[10px] text-emerald-700 dark:text-emerald-300"
                      >
                        {h.provider}
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="border-rose-500/40 text-[10px] text-rose-700 dark:text-rose-300"
                      >
                        FAIL
                      </Badge>
                    )}
                    {h.mock && (
                      <Badge
                        variant="outline"
                        className="border-amber-500/40 text-[10px] text-amber-700 dark:text-amber-300"
                      >
                        mock
                      </Badge>
                    )}
                    <span className="text-muted-foreground">
                      {h.tokensUsed} tokens
                    </span>
                  </div>
                  {h.fallbackChain.length > 0 && (
                    <div className="text-muted-foreground">
                      chain: {h.fallbackChain.join(" → ")}
                    </div>
                  )}
                  {h.detail && (
                    <div className="text-rose-700 dark:text-rose-300">{h.detail}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ProviderConfigModal
        provider={activeConfig}
        open={activeConfig !== null}
        onClose={() => setActiveConfig(null)}
        onSaved={() => {
          // A successful key save changes both the configured flag (status
          // query) and the cascade active set — refetch both so the cards
          // and chain reflect the new key without a manual reload.
          void queryClient.invalidateQueries({
            queryKey: ["admin", "providers"],
          });
          void queryClient.invalidateQueries({
            queryKey: ["admin", "providers", "status"],
          });
        }}
      />
    </div>
  );
}
