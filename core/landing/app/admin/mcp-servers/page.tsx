/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// External MCP servers — ABS as an MCP *client*. An organisation registers a
// third-party MCP server (GitHub / Slack / their own) here; ABS connects out,
// discovers its tools and (Slice 2) federates them into its catalog + agents.
// Distinct from /admin/mcp-tokens (which connects a client TO ABS).
"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Server,
  Plus,
  Trash2,
  Plug,
  CheckCircle2,
  XCircle,
  Loader2,
  ShieldAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface ServerRow {
  slug: string;
  name: string;
  url: string;
  transport: string;
  auth_type: string;
  header_name: string;
  has_auth: boolean;
  enabled: boolean;
  status: string;
  last_error: string | null;
  discovered_tool_count: number;
  last_checked_at: string | null;
  created_at: string | null;
}

interface TestResult {
  ok: boolean;
  tool_count?: number;
  tools?: { name: string; description: string }[];
  federated?: number;
  error?: string;
}

const SELECT_CLS =
  "rounded-md border border-border bg-background px-2 py-2 text-sm";

export default function McpServersPage() {
  const [servers, setServers] = useState<ServerRow[]>([]);
  const [disabled, setDisabled] = useState(false);
  const [loading, setLoading] = useState(true);

  // add form
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState("http");
  const [authType, setAuthType] = useState("none");
  const [secret, setSecret] = useState("");
  const [headerName, setHeaderName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // per-server test state
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/v1/admin/external-mcp", {
        credentials: "include",
      });
      if (res.status === 404) {
        setDisabled(true);
        setServers([]);
        return;
      }
      setDisabled(false);
      if (res.ok) {
        const data = await res.json();
        setServers(data.servers ?? []);
      }
    } catch {
      /* network — leave list as-is */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function add() {
    if (!name.trim() || !url.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      const res = await fetch("/v1/admin/external-mcp", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          url: url.trim(),
          transport,
          auth_type: authType,
          secret: authType === "none" ? "" : secret.trim(),
          header_name: authType === "header" ? headerName.trim() : "",
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        setAddError(`HTTP ${res.status}: ${t.slice(0, 200)}`);
        return;
      }
      setName("");
      setUrl("");
      setSecret("");
      setHeaderName("");
      setAuthType("none");
      await load();
    } catch (exc) {
      setAddError(exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setAdding(false);
    }
  }

  async function test(slug: string) {
    setTesting(slug);
    try {
      const res = await fetch(`/v1/admin/external-mcp/${slug}/test`, {
        method: "POST",
        credentials: "include",
      });
      const data = (await res.json()) as TestResult;
      setTestResults((prev) => ({ ...prev, [slug]: data }));
      await load();
    } catch (exc) {
      setTestResults((prev) => ({
        ...prev,
        [slug]: {
          ok: false,
          error: exc instanceof Error ? exc.message : "the test could not run",
        },
      }));
    } finally {
      setTesting(null);
    }
  }

  async function toggle(row: ServerRow) {
    await fetch(`/v1/admin/external-mcp/${row.slug}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !row.enabled }),
    });
    await load();
  }

  async function remove(slug: string) {
    await fetch(`/v1/admin/external-mcp/${slug}`, {
      method: "DELETE",
      credentials: "include",
    });
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[slug];
      return next;
    });
    await load();
  }

  return (
    <main data-page="admin-mcp-servers" className="mx-auto w-full max-w-4xl px-6 py-8">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6"
      >
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Server className="h-5 w-5 text-primary" />
          External MCP servers
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Add a third-party MCP server (GitHub, Slack, one of your own). ABS
          connects to it as a <strong>client</strong>, discovers its tools and
          adds them to its own catalogue and agents. (To connect a client to
          ABS instead, go to <code>MCP tokens</code>.)
        </p>
      </motion.header>

      {disabled && (
        <div
          data-test="mcp-servers-disabled"
          className="mb-6 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            This feature is switched off. To turn it on, set{" "}
            <code>ABS_EXTERNAL_MCP_ENABLED=true</code> on the server and restart
            the backend.
          </span>
        </div>
      )}

      {/* ── Add ──────────────────────────────────────── */}
      <Card className="mb-6 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Add a server</CardTitle>
          <CardDescription>
            Its endpoint URL, plus authentication if it needs any. Once added,
            hit &quot;Test&quot; to confirm the connection and see its tools.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name (e.g. GitHub MCP)"
              data-test="mcp-server-name"
            />
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://… /mcp"
              data-test="mcp-server-url"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-[140px_160px_1fr]">
            <select
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
              className={SELECT_CLS}
              aria-label="Transport"
              data-test="mcp-server-transport"
            >
              <option value="http">http (streamable)</option>
              <option value="sse">sse</option>
            </select>
            <select
              value={authType}
              onChange={(e) => setAuthType(e.target.value)}
              className={SELECT_CLS}
              aria-label="Authentication"
              data-test="mcp-server-auth"
            >
              <option value="none">no auth</option>
              <option value="bearer">Bearer token</option>
              <option value="header">Custom header</option>
            </select>
            {authType === "header" && (
              <Input
                value={headerName}
                onChange={(e) => setHeaderName(e.target.value)}
                placeholder="Header name (e.g. X-API-Key)"
                data-test="mcp-server-header-name"
              />
            )}
          </div>
          {authType !== "none" && (
            <Input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={authType === "bearer" ? "Bearer token" : "Header value"}
              data-test="mcp-server-secret"
            />
          )}
          <Button
            onClick={() => void add()}
            disabled={adding || !name.trim() || !url.trim()}
            data-test="mcp-server-add"
          >
            <Plus className="mr-2 h-4 w-4" />
            {adding ? "Adding…" : "Add"}
          </Button>
          {addError && (
            <div
              data-test="mcp-server-add-error"
              className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200"
            >
              {addError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── List ─────────────────────────────────────── */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : servers.length === 0 && !disabled ? (
        <p className="text-sm text-muted-foreground">
          No external MCP servers yet.
        </p>
      ) : (
        <div className="space-y-3" data-test="mcp-server-list">
          {servers.map((s) => {
            const tr = testResults[s.slug];
            return (
              <Card key={s.slug} className="bg-card/70">
                <CardContent className="space-y-3 pt-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        <StatusBadge status={s.status} />
                        {!s.enabled && (
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            disabled
                          </span>
                        )}
                      </div>
                      <div className="truncate font-mono text-xs text-muted-foreground">
                        {s.url}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        <span>transport: {s.transport}</span>
                        <span>· auth: {s.auth_type}</span>
                        <span>· {s.discovered_tool_count} tools</span>
                        {s.last_checked_at && (
                          <span suppressHydrationWarning>
                            · last tested:{" "}
                            {new Date(s.last_checked_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void test(s.slug)}
                        disabled={testing === s.slug}
                        data-test={`mcp-server-test-${s.slug}`}
                      >
                        {testing === s.slug ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <Plug className="mr-1 h-3 w-3" />
                        )}
                        Test
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void toggle(s)}
                        data-test={`mcp-server-toggle-${s.slug}`}
                      >
                        {s.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-rose-300"
                        onClick={() => void remove(s.slug)}
                        data-test={`mcp-server-remove-${s.slug}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  {s.last_error && s.status === "error" && (
                    <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-2 text-[11px] text-rose-200">
                      {s.last_error}
                    </div>
                  )}

                  {tr && (
                    <div
                      data-test={`mcp-server-testresult-${s.slug}`}
                      className={`rounded-md border p-2 text-xs ${
                        tr.ok
                          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                          : "border-rose-500/30 bg-rose-500/10 text-rose-200"
                      }`}
                    >
                      {tr.ok ? (
                        <>
                          <div className="mb-1 flex items-center gap-1 font-medium">
                            <CheckCircle2 className="h-3 w-3" /> Connected —{" "}
                            {tr.tool_count} tools found
                            {typeof tr.federated === "number" && tr.federated > 0 && (
                              <span className="ml-1 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px]">
                                {tr.federated} published to /mcp (ext_…)
                              </span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(tr.tools ?? []).slice(0, 24).map((t) => (
                              <span
                                key={t.name}
                                title={t.description}
                                className="rounded bg-background/60 px-1.5 py-0.5 font-mono text-[10px]"
                              >
                                {t.name}
                              </span>
                            ))}
                            {(tr.tools?.length ?? 0) > 24 && (
                              <span className="text-[10px]">
                                +{(tr.tools?.length ?? 0) - 24} more…
                              </span>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="flex items-center gap-1">
                          <XCircle className="h-3 w-3" /> {tr.error}
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    error: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    unconfigured: "border-border bg-muted text-muted-foreground",
  };
  const cls = map[status] ?? map.unconfigured;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${cls}`}>
      {status}
    </span>
  );
}
