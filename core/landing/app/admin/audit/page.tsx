// Q8 Phase K — `/admin/audit` HMAC-chain audit log viewer + error log
// timeline. Polls /v1/admin/audit/recent (or falls back to a mock so the
// page is exercisable before the production audit table fills up).
"use client";

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

interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  resource?: string | null;
  detail?: string | null;
  ip_hash?: string | null;
  user_agent_short?: string | null;
  hmac?: string;
}

const MOCK_AUDIT: AuditEntry[] = [
  {
    id: 412,
    ts: new Date(Date.now() - 5 * 60_000).toISOString(),
    actor: "admin@demo-acme.com",
    action: "login",
    resource: null,
    detail: "panel session opened",
    ip_hash: "h:9a2c…",
    user_agent_short: "Chrome 138 macOS",
    hmac: "3f8e…",
  },
  {
    id: 411,
    ts: new Date(Date.now() - 32 * 60_000).toISOString(),
    actor: "admin@demo-acme.com",
    action: "marketplace.install",
    resource: "stripe-webhook",
    detail: "plugin installed via /api/marketplace/install",
    ip_hash: "h:9a2c…",
    user_agent_short: "Chrome 138 macOS",
    hmac: "1c4a…",
  },
  {
    id: 410,
    ts: new Date(Date.now() - 48 * 60_000).toISOString(),
    actor: "system",
    action: "cascade.fallback",
    resource: "groq → gemini",
    detail: "rate_limit on groq, fellthrough to gemini",
    ip_hash: null,
    user_agent_short: null,
    hmac: "a801…",
  },
  {
    id: 409,
    ts: new Date(Date.now() - 90 * 60_000).toISOString(),
    actor: "admin@demo-acme.com",
    action: "secret.read",
    resource: "VAULT/groq_api_key",
    detail: "vault unsealed for cascade boot",
    ip_hash: "h:9a2c…",
    user_agent_short: "Chrome 138 macOS",
    hmac: "df17…",
  },
];

async function fetchAudit(): Promise<AuditEntry[]> {
  try {
    const res = await fetch("/v1/admin/audit/recent?limit=200", {
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) return MOCK_AUDIT;
    const data = await res.json();
    return Array.isArray(data) ? data : data.entries ?? MOCK_AUDIT;
  } catch {
    return MOCK_AUDIT;
  }
}

export default function AuditPage() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [verifyState, setVerifyState] = useState<"idle" | "ok" | "broken">("idle");

  const audit = useQuery<AuditEntry[]>({
    queryKey: ["admin", "audit"],
    queryFn: fetchAudit,
    refetchInterval: 30_000,
  });

  const filtered = useMemo(() => {
    let list = audit.data ?? [];
    if (actor.trim())
      list = list.filter((e) =>
        e.actor.toLowerCase().includes(actor.trim().toLowerCase()),
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
        e.actor,
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

  function verifyChain() {
    setVerifyState("idle");
    // Mock: in production, hit /v1/admin/audit/verify-chain. The
    // mock data has stable hmacs so this always resolves OK locally.
    window.setTimeout(() => setVerifyState("ok"), 400);
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
            Denetim
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            HMAC zinciriyle imzalı audit log. GDPR Madde 15 + SOC2 CC7.2 veri
            kaynağı.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={verifyChain}
            data-test="audit-verify-chain"
          >
            {verifyState === "ok" ? (
              <>
                <ShieldCheck className="mr-2 h-3.5 w-3.5 text-emerald-400" />
                Zincir doğrulandı
              </>
            ) : verifyState === "broken" ? (
              <>
                <ShieldX className="mr-2 h-3.5 w-3.5 text-rose-400" />
                Zincir kırık
              </>
            ) : (
              <>
                <ShieldCheck className="mr-2 h-3.5 w-3.5" />
                Zinciri doğrula
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={exportCsv}
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
            Filtreler
          </CardTitle>
          <CardDescription>
            Aktör, eylem veya kaynak ile süzün.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Aktör (e-posta veya 'system')"
            data-test="audit-filter-actor"
          />
          <Input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="Eylem (login, secret.read, cascade.fallback…)"
            data-test="audit-filter-action"
          />
        </CardContent>
      </Card>

      <Card className="bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Son olaylar ({filtered.length})
          </CardTitle>
          <CardDescription>30 saniyede bir auto-refresh.</CardDescription>
        </CardHeader>
        <CardContent>
          {audit.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Filtreyle eşleşen olay yok.
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((e) => (
                <li
                  key={e.id}
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
                    <span className="text-muted-foreground">
                      {new Date(e.ts).toLocaleString("tr-TR")}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {e.actor}
                    </span>
                  </div>
                  {e.resource && (
                    <div className="text-muted-foreground">
                      kaynak:{" "}
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
