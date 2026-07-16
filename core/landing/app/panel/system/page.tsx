/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// /admin/system — Delivery & errors.
//
// The backend has watched outbound delivery failures for a while
// (/v1/admin/errors/recent: webhook posts and queued emails that errored) but
// nothing surfaced them, so an operator whose Slack post or magic-link email
// silently failed had no way to see why. This is that surface: the real rows,
// newest first, with an honest empty state when nothing has failed.
"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Mail, RefreshCw, Webhook } from "lucide-react";

type Severity = "error" | "warn";
type ErrorRow = {
  source: "webhook" | "email";
  id: string | number;
  ts: string | null;
  severity: Severity;
  message: string;
};

type Filter = "all" | "error" | "warn";

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function SystemDeliveryPage() {
  const [rows, setRows] = useState<ErrorRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((sev: Filter) => {
    setRefreshing(true);
    fetch(`/v1/admin/errors/recent?limit=200&severity=${sev}`, {
      credentials: "include",
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`The server answered ${r.status}.`))))
      .then((d: { errors: ErrorRow[] }) => {
        setRows(d.errors);
        setError(null);
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    load(filter);
  }, [filter, load]);

  const counts = rows
    ? {
        error: rows.filter((r) => r.severity === "error").length,
        warn: rows.filter((r) => r.severity === "warn").length,
      }
    : null;

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Delivery &amp; errors
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Outbound messages this server tried to send and couldn&apos;t —
            failed webhook posts and queued emails. If an integration went quiet,
            the reason is here.
          </p>
        </div>
        <button
          type="button"
          onClick={() => load(filter)}
          disabled={refreshing}
          className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(["all", "error", "warn"] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors ${
              filter === f
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-accent"
            }`}
          >
            {f}
            {counts && f === "error" ? ` · ${counts.error}` : ""}
            {counts && f === "warn" ? ` · ${counts.warn}` : ""}
          </button>
        ))}
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
        >
          {error}
        </p>
      )}

      {!rows && !error && (
        <div className="h-40 w-full animate-pulse rounded-md bg-muted/40" />
      )}

      {rows && rows.length === 0 && !error && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-6 py-14 text-center">
          <CheckCircle2 className="h-8 w-8 text-emerald-600 dark:text-emerald-400" />
          <p className="text-sm font-medium text-foreground">
            Nothing has failed to send.
          </p>
          <p className="max-w-sm text-xs text-muted-foreground">
            Every webhook and email this server has sent went through. Failed
            deliveries would appear here with the error the provider returned.
          </p>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Source</th>
                <th className="px-4 py-2.5 font-medium">When</th>
                <th className="px-4 py-2.5 font-medium">Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={`${r.source}-${r.id}`}
                  className="border-b border-border/50 last:border-0"
                >
                  <td className="whitespace-nowrap px-4 py-3 align-top">
                    <span className="inline-flex items-center gap-1.5">
                      {r.source === "webhook" ? (
                        <Webhook className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <span className="text-xs capitalize text-foreground">{r.source}</span>
                      <SeverityChip severity={r.severity} />
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 align-top font-mono text-xs text-muted-foreground">
                    {fmt(r.ts)}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className="break-words font-mono text-xs text-foreground">
                      {r.message}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SeverityChip({ severity }: { severity: Severity }) {
  const isError = severity === "error";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
        isError
          ? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
          : "bg-amber-500/10 text-amber-700 dark:text-amber-300"
      }`}
    >
      <AlertTriangle className="h-2.5 w-2.5" />
      {isError ? "failed" : "retrying"}
    </span>
  );
}
