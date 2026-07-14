/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Split-shell for /admin/users.
//
// Server-side fetches the current users list with the caller's session
// cookie forwarded, hands the array to <UsersClient> as `initialUsers`,
// and the client island uses it as React Query `initialData` so the
// first paint already renders the table.
//
// LCP target on slow 3G: ~−400 ms vs the previous client-only shape
// (eliminates the post-hydration round-trip to /v1/admin/users).
//
// When the fetch fails, this page says so. It used to fall back to sample rows,
// which meant an admin whose session hiccuped was shown a roster of people who
// do not exist — including an account called admin@demo-acme.com holding admin
// on their server. Whoever saw that was right to be alarmed and wrong about why.
// It also hid the opposite failure: a real roster that would not load looked
// like a populated one.
import { cookies } from "next/headers";

import UsersClient from "./UsersClient";
import type { UserRow } from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// SWEEP — unique <title> per panel/admin page.
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "Users — ABS Admin",
  robots: { index: false, follow: false },
};

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

interface UsersLoad {
  users: UserRow[];
  loadError: string | null;
}

async function fetchUsersServerSide(): Promise<UsersLoad> {
  try {
    const cookieStore = await cookies();
    const cookieHeader = cookieStore
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");

    const res = await fetch(`${BACKEND_URL}/v1/admin/users`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
      cache: "no-store",
    });
    if (!res.ok) {
      return { users: [], loadError: `The server answered ${res.status}.` };
    }
    const data = await res.json();
    if (Array.isArray(data)) return { users: data as UserRow[], loadError: null };
    if (data && Array.isArray((data as { users?: unknown }).users)) {
      return { users: (data as { users: UserRow[] }).users, loadError: null };
    }
    return { users: [], loadError: "The server sent back a reply we could not read." };
  } catch {
    return { users: [], loadError: "The server could not be reached." };
  }
}

export default async function UsersPage() {
  const { users, loadError } = await fetchUsersServerSide();
  return <UsersClient initialUsers={users} loadError={loadError} />;
}
