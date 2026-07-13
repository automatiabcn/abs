/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The live signals the shell chrome renders: how many approvals wait on the
// operator, and how many providers are standing. Both endpoints already exist
// for their own pages; the shell only reads the headline number.
//
// Failure is quiet by design: a signal that cannot be fetched returns null and
// the chrome simply shows nothing — a broken status poll must never make the
// navigation itself look alarming.
"use client";

import { useQuery } from "@tanstack/react-query";

export interface ShellStatus {
  /** Approvals waiting on the operator, or null while unknown. */
  pending: number | null;
  providersUp: number | null;
  providersTotal: number | null;
}

async function fetchPending(): Promise<number> {
  const res = await fetch("/v1/approvals?status=pending", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as {
    pending_total?: number;
    items?: unknown[];
  };
  if (typeof data.pending_total === "number") return data.pending_total;
  return data.items?.length ?? 0;
}

async function fetchProviders(): Promise<{ up: number; total: number }> {
  const res = await fetch("/v1/cascade/providers", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as { active?: string[]; total?: number };
  const up = data.active?.length ?? 0;
  return { up, total: data.total ?? up };
}

export function useShellStatus(): ShellStatus {
  const approvals = useQuery({
    queryKey: ["shell", "approvals-pending"],
    queryFn: fetchPending,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: false,
  });

  const providers = useQuery({
    queryKey: ["shell", "providers"],
    queryFn: fetchProviders,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  return {
    pending: approvals.data ?? null,
    providersUp: providers.data?.up ?? null,
    providersTotal: providers.data?.total ?? null,
  };
}
