/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2B BUG-33 — Provider Yapılandır modal.
//
// Read-only window over the operator's stored API key (masked, never the
// full value) plus a "Şimdi test et" button that hits
// `POST /v1/admin/providers/{id}/test` and renders latency or error.
// In-place save of the API key is intentionally OUT of scope for rc7;
// the secondary CTA links to /setup/step/providers where the customer
// onboard wizard already ships a full save flow. Sprint 2C lands the
// in-place edit endpoint.
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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
}: ProviderConfigModalProps) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset transient state whenever the modal target changes.
  useEffect(() => {
    setResult(null);
    setError(null);
    setTesting(false);
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
      setError(exc instanceof Error ? exc.message : "bilinmeyen hata");
    } finally {
      setTesting(false);
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
          {provider.label} sağlayıcı ayarları
        </h2>

        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Durum</dt>
            <dd>
              {provider.configured ? (
                <Badge
                  variant="outline"
                  className="border-emerald-500/40 text-emerald-300"
                >
                  Yapılandırıldı
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="border-rose-500/40 text-rose-300"
                >
                  Eksik
                </Badge>
              )}
            </dd>
          </div>

          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">API anahtarı</dt>
            <dd className="font-mono text-xs">
              {maskedHint(provider.configured)}
            </dd>
          </div>

          <p className="text-xs text-muted-foreground">
            Anahtar tarayıcıya hiçbir zaman gönderilmez. Test yalnızca
            backend üzerinden tek-tokenlik bir denemedir.
          </p>
        </dl>

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
                  Başarılı — {result.latency_ms} ms
                  {result.model ? ` · ${result.model}` : ""}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <XCircle className="h-4 w-4" />
                <span>
                  Hata: {result.error ?? "bilinmeyen"} ({result.latency_ms} ms)
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
            Transport hatası: {error}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            data-testid="provider-config-cancel"
          >
            Kapat
          </Button>
          <Link
            href="/setup/step/providers"
            className="inline-flex items-center justify-center rounded-md border border-border px-3 py-2 text-sm hover:bg-accent"
            data-testid="provider-config-edit-link"
          >
            API anahtarını değiştir
          </Link>
          <Button
            type="button"
            onClick={runTest}
            disabled={testing || !provider.configured}
            data-testid="provider-config-test"
          >
            {testing ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                Test ediliyor…
              </>
            ) : (
              "Şimdi test et"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
