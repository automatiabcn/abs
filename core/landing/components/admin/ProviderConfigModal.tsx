/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The provider settings dialog.
//
// Shows the operator's stored API key (masked, never the full value), a
// "Test it now" button (`POST /v1/admin/providers/{id}/test`), AND an
// in-place key edit form that POSTs the new key to
// `POST /v1/admin/providers/{id}` (the Sprint 2C save endpoint). Previously
// the only edit path was a link to /setup/step/providers, which 404s /
// redirects to /admin once initial setup is complete — so post-setup the
// operator had no working way to rotate a provider key from the panel.
"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export interface ProviderConfigEntry {
  id: string;
  label: string;
  configured: boolean;
}

interface TestResult {
  ok: boolean;
  provider: string;
  model?: string | null;
  latency_ms: number;
  error?: string;
}

export interface ProviderConfigModalProps {
  provider: ProviderConfigEntry | null;
  open: boolean;
  onClose: () => void;
  /** Called after a successful key save so the parent can refetch status. */
  onSaved?: () => void;
}

function maskedHint(configured: boolean): string {
  // The actual key never leaves the backend — the modal only renders a
  // synthetic mask so the operator knows whether *something* is stored
  // without exposing the trailing 4 chars (which would be enough for an
  // attacker who shoulder-surfed once to recognise it later).
  return configured ? "sk-••••••••••••" : "—";
}

export default function ProviderConfigModal({
  provider,
  open,
  onClose,
  onSaved,
}: ProviderConfigModalProps) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // In-place key edit state.
  const [editing, setEditing] = useState(false);
  const [newKey, setNewKey] = useState("");
  // Cloudflare Workers AI needs an account id beside the token.
  const [accountId, setAccountId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const isCloudflare = provider?.id === "cloudflare";

  // Reset transient state whenever the modal target changes.
  useEffect(() => {
    setResult(null);
    setError(null);
    setTesting(false);
    setEditing(false);
    setNewKey("");
    setAccountId("");
    setSaving(false);
    setSaveErr(null);
    setSaved(false);
  }, [provider?.id]);

  // ESC closes the modal — match MarketplacePanel keyboard contract.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open || !provider) return null;

  async function runTest() {
    if (!provider) return;
    setTesting(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(
        `/v1/admin/providers/${encodeURIComponent(provider.id)}/test`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        },
      );
      if (!res.ok) {
        const body = await res.text();
        setError(`HTTP ${res.status}: ${body.slice(0, 160)}`);
        return;
      }
      const data = (await res.json()) as TestResult;
      setResult(data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setTesting(false);
    }
  }

  async function saveKey() {
    if (!provider || !newKey.trim()) return;
    setSaving(true);
    setSaveErr(null);
    setSaved(false);
    try {
      const res = await fetch(
        `/v1/admin/providers/${encodeURIComponent(provider.id)}`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: newKey.trim(),
            enabled: true,
            ...(isCloudflare && accountId.trim()
              ? { account_id: accountId.trim() }
              : {}),
          }),
        },
      );
      if (!res.ok) {
        const body = await res.text();
        setSaveErr(`HTTP ${res.status}: ${body.slice(0, 220)}`);
        return;
      }
      setSaved(true);
      setNewKey("");
      setAccountId("");
      setEditing(false);
      onSaved?.();
    } catch (exc) {
      setSaveErr(exc instanceof Error ? exc.message : "unknown error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      data-testid="provider-config-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="provider-config-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-md rounded-2xl bg-background p-6 shadow-xl ring-1 ring-border">
        <h2
          id="provider-config-modal-title"
          className="flex items-center gap-2 text-lg font-semibold tracking-tight"
        >
          <KeyRound className="h-4 w-4 text-primary" />
          {provider.label}
        </h2>

        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Status</dt>
            <dd>
              {provider.configured ? (
                <Badge
                  variant="outline"
                  className="border-emerald-500/40 text-emerald-300"
                >
                  Configured
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="border-rose-500/40 text-rose-300"
                >
                  Missing
                </Badge>
              )}
            </dd>
          </div>

          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">API key</dt>
            <dd className="font-mono text-xs">
              {maskedHint(provider.configured)}
            </dd>
          </div>

          <p className="text-xs text-muted-foreground">
            The key is stored encrypted on the server. It is never sent back to
            this page, so once saved you cannot read it again — only replace it.
          </p>
        </dl>

        {editing && (
          <div className="mt-4 space-y-2" data-testid="provider-key-edit">
            <label
              htmlFor="provider-new-key"
              className="block text-xs text-muted-foreground"
            >
              New API key
              {isCloudflare ? " — Cloudflare API token" : ""}
            </label>
            <input
              id="provider-new-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="sk-… / gsk_… / paste the key"
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
              data-testid="provider-key-input"
            />
            {isCloudflare && (
              <>
                <label
                  htmlFor="provider-account-id"
                  className="block text-xs text-muted-foreground"
                >
                  Cloudflare account ID
                </label>
                <input
                  id="provider-account-id"
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  placeholder="e.g. 1a2b3c4d… (the Workers AI account)"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
                  data-testid="provider-account-id-input"
                />
              </>
            )}
            {saveErr && (
              <div
                className="rounded-md border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200"
                data-testid="provider-key-save-error"
              >
                Not saved: {saveErr}
              </div>
            )}
          </div>
        )}

        {saved && (
          <div
            className="mt-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm text-emerald-200"
            data-testid="provider-key-saved"
          >
            ✓ Key saved, tested, and stored encrypted.
          </div>
        )}

        {result && (
          <div
            data-testid="provider-test-result"
            className={
              "mt-4 rounded-md border p-3 text-sm " +
              (result.ok
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-rose-500/30 bg-rose-500/10 text-rose-200")
            }
          >
            {result.ok ? (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4" />
                <span>
                  It answered in {result.latency_ms} ms
                  {result.model ? ` · ${result.model}` : ""}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <XCircle className="h-4 w-4" />
                <span>
                  It refused: {result.error ?? "no reason given"} (
                  {result.latency_ms} ms)
                </span>
              </div>
            )}
          </div>
        )}

        {error && (
          <div
            data-testid="provider-test-transport-error"
            className="mt-4 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200"
          >
            Could not reach the server: {error}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            data-testid="provider-config-cancel"
          >
            Close
          </Button>

          {editing ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setEditing(false);
                  setNewKey("");
                  setSaveErr(null);
                }}
                data-testid="provider-key-cancel"
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={saveKey}
                disabled={saving || !newKey.trim()}
                data-testid="provider-key-save"
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    Saving…
                  </>
                ) : (
                  "Save"
                )}
              </Button>
            </>
          ) : (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEditing(true);
                setSaved(false);
                setSaveErr(null);
              }}
              data-testid="provider-config-edit-link"
            >
              Replace the key
            </Button>
          )}

          <Button
            type="button"
            onClick={runTest}
            disabled={testing || !provider.configured}
            data-testid="provider-config-test"
          >
            {testing ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                Testing…
              </>
            ) : (
              "Test it now"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
