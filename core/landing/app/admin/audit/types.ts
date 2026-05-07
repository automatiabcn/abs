/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// R64 (S8) — shared between server page.tsx and AuditClient island so
// the two halves of the split-shell agree on the entry shape.

export interface AuditEntry {
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

export const MOCK_AUDIT: AuditEntry[] = [
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
