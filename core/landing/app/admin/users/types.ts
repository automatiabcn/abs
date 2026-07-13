/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// R65 (S8) — shared between server page.tsx and UsersClient island so
// the two halves of the split-shell agree on the row shape and the
// fallback fixture.

export interface UserRow {
  id: number;
  email: string;
  role: string;
  status: "pending" | "active" | "revoked";
  last_login?: string | null;
  created_at: string;
  magic_link?: string;
}
