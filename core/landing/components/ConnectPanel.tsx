"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


/**
 * Connect dashboard panel.
 *
 * Public-facing equivalent of `app/static/connect.html`. Asks for the admin
 * Bearer token client-side, fetches `/v1/smart-link/connected-services`, and
 * renders the provider grid.
 *
 * Token is held only in component state; never persisted.
 */

import * as React from "react";

interface Provider {
  id: string;
  name: string;
  auth_method: "oauth" | "api_key" | "credentials";
}

interface Connected {
  key_name: string;
  provider: string;
  created_at: string;
  last_validated_at: string | null;
  last_validated_ok: boolean | null;
  last_validated_error: string | null;
}

interface ConnectedServicesResponse {
  providers: Provider[];
  connected: Connected[];
  count: number;
}

const CONNECTED_SERVICES_URL = "/v1/smart-link/connected-services";

export default function ConnectPanel() {
  const [token, setToken] = React.useState("");
  const [data, setData] = React.useState<ConnectedServicesResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!token.trim()) {
      setError("Admin token required");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(CONNECTED_SERVICES_URL, {
        headers: { Authorization: "Bearer " + token.trim() },
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const json = (await res.json()) as ConnectedServicesResponse;
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [token]);

  const connectedMap = React.useMemo(() => {
    const m: Record<string, Connected> = {};
    if (data) {
      data.connected.forEach((c) => {
        m[c.provider] = c;
      });
    }
    return m;
  }, [data]);

  return (
    <section className="container mx-auto px-4 py-12" aria-labelledby="connect-title">
      <h1 id="connect-title" className="text-2xl font-bold tracking-tight">
        Connected Services
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Smart-link integrations for your ABS instance.
      </p>

      <div className="mt-4 flex items-center gap-2 rounded-lg border border-border bg-card p-3">
        <label htmlFor="admin-token" className="sr-only">
          Admin Bearer token
        </label>
        <input
          id="admin-token"
          type="password"
          placeholder="Admin Bearer token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="flex-1 rounded border border-border bg-background px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={load}
          disabled={loading || !token}
          className="rounded bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load"}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-500">
          {error}
        </p>
      )}

      {data && (
        <div
          className="mt-6 grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}
          data-testid="provider-grid"
        >
          {data.providers.map((p) => {
            const connected = connectedMap[p.id] ?? null;
            return (
              <div
                key={p.id}
                className={
                  "rounded-lg border p-4 " +
                  (connected
                    ? "border-primary bg-card"
                    : "border-border bg-card")
                }
              >
                <div className="text-sm font-semibold">{p.name}</div>
                <div className="text-xs text-muted-foreground">
                  auth: {p.auth_method}
                </div>
                <div className="mt-2 text-xs">
                  {connected
                    ? connected.last_validated_ok
                      ? "✓ validated"
                      : "✗ " +
                        (connected.last_validated_error ?? "never validated")
                    : "not connected"}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
