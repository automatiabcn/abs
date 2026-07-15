/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Split-shell client island for /admin/audit. Original
// logic from `page.tsx` lifted here verbatim; the only delta is that
// `initialEntries` from the server component seeds React Query as
// `initialData`, so the first paint already has rows and the page
// skips the post-hydration round-trip that previously cost ~400 ms
// on slow 3G.
"use client";

import { formatDateTime } from "@/lib/format";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Download,
  Filter,
  ShieldCheck,
  ShieldX,
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { AuditEntry } from "./types";

async function fetchAudit(): Promise<AuditEntry[]> {
  const res = await fetch("/v1/admin/audit/recent?limit=200", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`audit_fetch_${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.entries ?? []);
}

interface AuditClientProps {
  initialEntries: AuditEntry[];
  /** Set when the server-side fetch failed. Non-null means: show that, show no rows. */
  loadError?: string | null;
}

export default function AuditClient({
  initialEntries,
  loadError = null,
}: AuditClientProps) {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [verifyState, setVerifyState] = useState<
    "idle" | "loading" | "ok" | "empty" | "broken" | "error"
  >("idle");
  const [verifyDetail, setVerifyDetail] = useState<string>("");

  const audit = useQuery<AuditEntry[]>({
    queryKey: ["admin", "audit"],
    queryFn: fetchAudit,
    refetchInterval: 30_000,
    initialData: initialEntries,
    initialDataUpdatedAt: 0,
  });

  // The log could not be read — from the server render, or from the 30-second
  // refresh, or both. We only say so while we genuinely have nothing: a failed
  // refresh on top of rows that did load is not worth throwing the rows away.
  const rowCount = audit.data?.length ?? 0;
  const failed = (loadError !== null || audit.isError) && rowCount === 0;

  const filtered = useMemo(() => {
    let list = audit.data ?? [];
    if (actor.trim())
      list = list.filter((e) =>
        (e.actor ?? "").toLowerCase().includes(actor.trim().toLowerCase()),
      );
    if (action.trim())
      list = list.filter((e) =>
        e.action.toLowerCase().includes(action.trim().toLowerCase()),
      );
    return list;
  }, [audit.data, actor, action]);

  function exportCsv() {
    const rows = [
      ["id", "ts", "actor", "action", "resource", "detail", "hmac"],
      ...filtered.map((e) => [
        String(e.id),
        e.ts,
        e.actor ?? "",
        e.action,
        e.resource ?? "",
        (e.detail ?? "").replace(/[\r\n]/g, " "),
        e.hmac ?? "",
      ]),
    ];
    const csv = rows
      .map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `abs-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function verifyChain() {
    setVerifyState("loading");
    setVerifyDetail("");
    try {
      const res = await fetch("/v1/admin/audit/verify-chain", {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`verify_${res.status}`);
      const r = await res.json();
      const checked = Number(r.total_entries ?? 0);
      if (r.ok && checked === 0) {
        // An empty chain is not tampered with, so the API is right to say ok.
        // But "Log intact" over nothing checked is a green tick on no work — and
        // it is exactly what this button showed for months while the recorder
        // was writing to a logger with no handler and the page below was
        // rendering fabricated rows. Whatever else is true, an empty log is a
        // thing the operator needs to know about, not be reassured about.
        setVerifyState("empty");
        setVerifyDetail("");
      } else if (r.ok) {
        setVerifyState("ok");
        setVerifyDetail(`${checked} entries checked`);
      } else {
        setVerifyState("broken");
        setVerifyDetail(
          r.tampered_entry_id != null
            ? `altered at #${r.tampered_entry_id}`
            : "",
        );
      }
    } catch {
      setVerifyState("error");
    }
  }

  return (
    <main
      data-page="admin-audit"
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
            <ShieldCheck className="h-5 w-5 text-primary" />
            Audit
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What happened on this server and who did it. Every entry is signed
            and chained, so a deleted or edited record shows up. Export it for
            GDPR Article 15 or SOC 2 CC7.2 evidence.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={verifyChain}
            disabled={verifyState === "loading"}
            data-test="audit-verify-chain"
          >
            {verifyState === "loading" ? (
              <>
                <ShieldCheck className="mr-2 h-3.5 w-3.5 animate-pulse" />
                Checking…
              </>
            ) : verifyState === "ok" ? (
              <>
                <ShieldCheck className="mr-2 h-3.5 w-3.5 text-emerald-400" />
                Log intact{verifyDetail ? ` · ${verifyDetail}` : ""}
              </>
            ) : verifyState === "empty" ? (
              <>
                <ShieldX className="mr-2 h-3.5 w-3.5 text-amber-400" />
                Nothing recorded yet
              </>
            ) : verifyState === "broken" ? (
              <>
                <ShieldX className="mr-2 h-3.5 w-3.5 text-rose-400" />
                Log tampered with{verifyDetail ? ` · ${verifyDetail}` : ""}
              </>
            ) : verifyState === "error" ? (
              <>
                <ShieldX className="mr-2 h-3.5 w-3.5 text-amber-400" />
                Check failed — try again
              </>
            ) : (
              <>
                <ShieldCheck className="mr-2 h-3.5 w-3.5" />
                Check the log
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={exportCsv}
            // Nothing was read, so there is nothing to hand to an auditor.
            disabled={failed}
            data-test="audit-export"
          >
            <Download className="mr-2 h-3.5 w-3.5" />
            CSV
          </Button>
        </div>
      </motion.header>

      <Card className="mb-4 bg-card/60">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="h-4 w-4 text-primary" />
            Filters
          </CardTitle>
          <CardDescription>
            Narrow the log down to a person or an action.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Who (an email, or 'system')"
            data-test="audit-filter-actor"
          />
          <Input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="What (login, secret.read, cascade.fallback…)"
            data-test="audit-filter-action"
          />
        </CardContent>
      </Card>

      <Card className="bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Recent events ({filtered.length})
          </CardTitle>
          <CardDescription>Refreshes every 30 seconds.</CardDescription>
        </CardHeader>
        <CardContent>
          {failed ? (
            <div
              data-test="audit-load-error"
              className="rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm"
            >
              <p className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
                <ShieldX className="h-4 w-4" />
                The audit log could not be read
              </p>
              <p className="mt-1 text-muted-foreground">
                {loadError ?? "The server could not be reached."} No entries are
                shown, because showing anything here that did not come from the
                log would be worse than showing nothing. This does not mean
                nothing happened — it means we cannot currently tell you what
                did.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => audit.refetch()}
                data-test="audit-retry"
              >
                Try again
              </Button>
            </div>
          ) : audit.isLoading && filtered.length === 0 ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No events match these filters.
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((e, i) => (
                <li
                  // The chain can carry more than one entry per id (the seed and
                  // some batched writes reuse a sequence), so id alone is not a
                  // unique React key — compose it with the row index.
                  key={`${e.id}-${i}`}
                  data-test="audit-row"
                  data-action={e.action}
                  className={cn(
                    "rounded-md border border-border bg-background/40 p-3 text-xs",
                    e.actor === "system" && "border-amber-500/30",
                  )}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-muted-foreground">
                      #{e.id}
                    </span>
                    <Badge variant="outline" className="font-mono">
                      {e.action}
                    </Badge>
                    {/* Rendered in the viewer's own locale and time zone, so
                        the server (UTC container) and the client can disagree
                        on the string — suppress the hydration warning rather
                        than pin a locale nobody asked for (React #418). */}
                    <span
                      className="text-muted-foreground"
                      suppressHydrationWarning
                    >
                      {formatDateTime(new Date(e.ts), "en")}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {e.actor}
                    </span>
                  </div>
                  {e.resource && (
                    <div className="text-muted-foreground">
                      resource:{" "}
                      <code className="font-mono">{e.resource}</code>
                    </div>
                  )}
                  {e.detail && <div className="text-foreground/90">{e.detail}</div>}
                  {e.hmac && (
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      hmac: <code className="font-mono">{e.hmac}</code>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
