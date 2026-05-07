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

export const MOCK_USERS: UserRow[] = [
  {
    id: 1,
    email: "admin@demo-acme.com",
    role: "admin",
    status: "active",
    last_login: new Date().toISOString(),
    created_at: "2026-04-29T10:00:00Z",
  },
  {
    id: 2,
    email: "ops@demo-acme.com",
    role: "operator",
    status: "active",
    last_login: new Date(Date.now() - 3600_000 * 6).toISOString(),
    created_at: "2026-04-30T09:00:00Z",
  },
  {
    id: 3,
    email: "intern@demo-acme.com",
    role: "viewer",
    status: "pending",
    last_login: null,
    created_at: new Date(Date.now() - 3600_000 * 2).toISOString(),
    magic_link: "https://abs.demo-acme.com/auth/magic?token=mock_t0ken_12ab",
  },
];
