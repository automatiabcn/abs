// R65 (S8) — Sprint 22 RSC Phase B leg 2: split-shell for /admin/users.
//
// Server-side fetches the current users list with the caller's session
// cookie forwarded, hands the array to <UsersClient> as `initialUsers`,
// and the client island uses it as React Query `initialData` so the
// first paint already renders the table.
//
// LCP target on slow 3G: ~−400 ms vs the previous client-only shape
// (eliminates the post-hydration round-trip to /v1/admin/users).
//
// On any auth/transport failure the server falls back to MOCK_USERS —
// same behaviour as the pre-R65 client `fetchUsers`.
import { cookies } from "next/headers";

import UsersClient from "./UsersClient";
import { MOCK_USERS, type UserRow } from "./types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

async function fetchUsersServerSide(): Promise<UserRow[]> {
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
    if (!res.ok) return MOCK_USERS;
    const data = await res.json();
    if (Array.isArray(data)) return data as UserRow[];
    if (data && Array.isArray((data as { users?: unknown }).users)) {
      return (data as { users: UserRow[] }).users;
    }
    return MOCK_USERS;
  } catch {
    return MOCK_USERS;
  }
}

export default async function UsersPage() {
  const initialUsers = await fetchUsersServerSide();
  return <UsersClient initialUsers={initialUsers} />;
}
