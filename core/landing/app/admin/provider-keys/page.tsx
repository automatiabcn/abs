/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// BYOK provider-key management. The per-owner key infra (encrypted store, RLS,
// project→user→org→global cascade resolution) was already production-ready but
// headless; this is the self-serve surface. Add / test / delete keys scoped to
// org · user · project. Plaintext is never returned — keys show only as
// metadata + a "validated" badge driven by POST /v1/admin/provider-keys/test.
"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound, Trash2, CheckCircle2, XCircle, CircleHelp } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const PROVIDERS = ["groq", "gemini", "cerebras", "cohere", "anthropic", "cloudflare"];
const OWNER_TYPES = ["org", "user", "project"] as const;

interface ProviderKeyRow {
  provider: string;
  owner_type: string;
  owner_id: string;
  created_at: string | null;
  updated_at: string | null;
  last_validated_ok: boolean | null;
}

export default function ProviderKeysPage() {
  const [keys, setKeys] = useState<ProviderKeyRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // add form
  const [provider, setProvider] = useState("groq");
  const [ownerType, setOwnerType] = useState<(typeof OWNER_TYPES)[number]>("org");
  const [ownerId, setOwnerId] = useState("");
  const [value, setValue] = useState("");
  const [probe, setProbe] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch("/v1/admin/provider-keys", { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: { keys: ProviderKeyRow[] }) => { setKeys(j.keys); setErr(null); })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => { load(); }, [load]);

  function scopeBody() {
    return {
      provider,
      owner_type: ownerType,
      owner_id: ownerType === "org" ? undefined : ownerId.trim() || undefined,
    };
  }

  async function save() {
    if (!value.trim()) return;
    setBusy(true);
    setErr(null);
    setProbe(null);
    try {
      const r = await fetch("/v1/admin/provider-keys", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...scopeBody(), value: value.trim() }),
      });
      if (!r.ok) { setErr(`Could not save the key (HTTP ${r.status}).`); return; }
      setValue("");
      // Saving used to be the end of it: the row appeared as "not checked yet"
      // and stayed that way, so a key with a typo in it sat in the panel looking
      // installed until the day someone asked a question and the answer did not
      // come. The save proves itself now.
      await fetch("/v1/admin/provider-keys/test", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(scopeBody()),
      }).catch(() => undefined);
      load();
    } catch { setErr("Could not save — the server did not answer."); }
    finally { setBusy(false); }
  }

  // Test the typed value BEFORE saving (pre-save probe).
  async function probeValue() {
    if (!value.trim()) return;
    setBusy(true);
    setProbe(null);
    try {
      const r = await fetch("/v1/admin/provider-keys/test", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...scopeBody(), value: value.trim() }),
      });
      const j = await r.json().catch(() => ({}));
      setProbe(j.ok ? "✓ The key works" : `✗ ${j.reason || "the provider rejected this key"}`);
    } catch { setProbe("✗ The server did not answer the test."); }
    finally { setBusy(false); }
  }

  // Test a STORED key (persists last_validated_ok).
  async function testStored(row: ProviderKeyRow) {
    setBusy(true);
    try {
      await fetch("/v1/admin/provider-keys/test", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          provider: row.provider,
          owner_type: row.owner_type,
          owner_id: row.owner_type === "org" ? undefined : row.owner_id,
        }),
      });
      load();
    } finally { setBusy(false); }
  }

  async function remove(row: ProviderKeyRow) {
    if (!window.confirm(`Remove your ${row.provider} key (${row.owner_type})? Questions will go back to the free providers.`)) return;
    setBusy(true);
    try {
      await fetch("/v1/admin/provider-keys", {
        method: "DELETE",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          provider: row.provider,
          owner_type: row.owner_type,
          owner_id: row.owner_type === "org" ? undefined : row.owner_id,
        }),
      });
      load();
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <KeyRound className="h-5 w-5 text-primary" /> Your provider keys
        </h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Bring your own provider. A key you add here answers your questions first,
          and the free providers stay behind it as the fallback — so you keep working
          even when your provider is down or out of quota. A key on a project beats one
          on your account, which beats one on the organisation. Keys are stored
          encrypted and never shown again.
        </p>
      </div>

      {/* Add form */}
      <Card className="mb-6 bg-card/60">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Add a key</CardTitle>
          <CardDescription>Check it works before you save it.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Provider</span>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}
                data-test="pk-provider"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm">
                {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-[12px]">
              <span className="text-muted-foreground">Applies to</span>
              <select value={ownerType} onChange={(e) => setOwnerType(e.target.value as typeof ownerType)}
                data-test="pk-owner-type"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm">
                <option value="org">everyone in the organisation</option>
                <option value="user">one person</option>
                <option value="project">one project</option>
              </select>
            </label>
            {ownerType !== "org" && (
              <label className="space-y-1 text-[12px]">
                <span className="text-muted-foreground">
                  {ownerType === "project" ? "Project *" : "Person (leave empty for yourself)"}
                </span>
                <Input value={ownerId} onChange={(e) => setOwnerId(e.target.value)}
                  data-test="pk-owner-id"
                  placeholder={ownerType === "project" ? "proje-slug" : "email"} />
              </label>
            )}
          </div>
          <Input type="password" value={value} onChange={(e) => setValue(e.target.value)}
            data-test="pk-value" placeholder="API key" />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={save} disabled={busy || !value.trim()} data-test="pk-save">
              Save
            </Button>
            <Button type="button" variant="outline" onClick={probeValue}
              disabled={busy || !value.trim()} data-test="pk-probe">
              Test it
            </Button>
            {probe && (
              <span data-test="pk-probe-result"
                className={probe.startsWith("✓") ? "text-xs text-emerald-400" : "text-xs text-rose-400"}>
                {probe}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {err && (
        <div className="mb-4 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {err}
        </div>
      )}

      {/* Key list */}
      <Card className="bg-card/60">
        <CardHeader className="pb-2"><CardTitle className="text-base">Your keys</CardTitle></CardHeader>
        <CardContent>
          {keys === null ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : keys.length === 0 ? (
            <p className="text-xs text-muted-foreground" data-test="pk-empty">No keys yet — you are on the free providers.</p>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">Provider</th>
                  <th className="pb-2 pr-3 font-medium">Applies to</th>
                  <th className="pb-2 pr-3 font-medium">Checked</th>
                  <th className="pb-2 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {keys.map((k, i) => (
                  <tr key={`${k.provider}-${k.owner_type}-${k.owner_id}-${i}`} data-test="pk-row">
                    <td className="py-2.5 pr-3 font-medium">{k.provider}</td>
                    <td className="py-2.5 pr-3 text-muted-foreground">
                      {k.owner_type}{k.owner_type !== "org" ? `:${k.owner_id}` : ""}
                    </td>
                    <td className="py-2.5 pr-3">
                      {k.last_validated_ok === true ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400" data-test="pk-validated">
                          <CheckCircle2 className="h-3.5 w-3.5" /> working
                        </span>
                      ) : k.last_validated_ok === false ? (
                        <span className="inline-flex items-center gap-1 text-rose-400">
                          <XCircle className="h-3.5 w-3.5" /> rejected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          <CircleHelp className="h-3.5 w-3.5" /> not checked yet
                        </span>
                      )}
                    </td>
                    <td className="py-2.5">
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => testStored(k)} disabled={busy}
                          data-test="pk-test" className="rounded-md border px-2.5 py-1 text-[11px]">
                          Test
                        </button>
                        <button type="button" onClick={() => remove(k)} disabled={busy}
                          data-test="pk-delete"
                          className="inline-flex items-center gap-1 rounded-md border border-rose-500/40 px-2.5 py-1 text-[11px] text-rose-300">
                          <Trash2 className="h-3 w-3" /> Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
