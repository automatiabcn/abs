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
