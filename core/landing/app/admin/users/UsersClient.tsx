/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Split-shell client island for /admin/users. Original
// logic from `page.tsx` lifted here verbatim; the only delta is that
// `initialUsers` from the server component seeds React Query as
// `initialData` so first paint already renders rows.
"use client";

import { formatDate, formatDateTime } from "@/lib/format";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Mail,
  Users as UsersIcon,
  UserCog,
  UserPlus,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { UserRow } from "./types";

async function fetchUsers(): Promise<UserRow[]> {
  const res = await fetch("/v1/admin/users", {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`users_fetch_${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? data : (data.users ?? []);
}

interface InviteResponse {
  invite_id: string;
  email: string;
  role: string;
  tenant_id?: string;
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at?: string | null;
  // When SMTP is configured the backend emails the magic-link and these
  // stay (true / undefined). On a no-SMTP self-host the email can't be
  // delivered, so the backend returns email_sent:false + the magic_url for
  // the admin to copy and hand over manually.
  email_sent?: boolean;
  magic_url?: string;
  activation_note?: string;
}

// Real invite endpoint. The backend persists a
// tenant_invites row and hashes the magic-link token. When SMTP is set it
// emails the recipient and withholds the URL; when SMTP is unset it returns
// the magic_url so the admin can deliver the activation link out-of-band.
async function inviteUser(payload: {
  email: string;
  role: string;
}): Promise<InviteResponse> {
  const res = await fetch("/v1/admin/users/invite", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return (await res.json()) as InviteResponse;
}

// Role / status mutation. Backend guards the last-admin lockout (409
// last_admin_protected) and refuses cross-tenant ids (404).
async function updateUser(
  userId: number | string,
  body: { role?: string; status?: string },
): Promise<void> {
  const res = await fetch(`/v1/admin/users/${encodeURIComponent(String(userId))}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      const d = j?.detail;
      msg = (typeof d === "object" ? d?.detail || d?.error : d) || msg;
    } catch {
      /* keep generic */
    }
    throw new Error(msg);
  }
}

interface InvitesListResponse {
  invites: InviteResponse[];
  total: number;
}

async function fetchInvites(): Promise<InviteResponse[]> {
  try {
    const res = await fetch("/v1/admin/users/invites", {
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data = (await res.json()) as InvitesListResponse;
    return data.invites ?? [];
  } catch {
    return [];
  }
}

async function revokeInvite(inviteId: string): Promise<void> {
  const res = await fetch(`/v1/admin/users/invite/${encodeURIComponent(inviteId)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`revoke_${res.status}`);
  }
}

// Written for a dark panel, and the default theme is light: on it, a person's
// role measured 1.5:1 against its own chip — which is to say, who is an admin was
// the one thing this page could not tell you at a glance.
const ROLE_LABELS: Record<string, { label: string; tone: string }> = {
  admin: {
    label: "Admin",
    tone: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30",
  },
  operator: {
    label: "Operator",
    tone: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  },
  viewer: {
    label: "Viewer",
    tone: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30",
  },
};

const STATUS_TONE: Record<UserRow["status"], string> = {
  active: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
  pending: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  revoked: "border-rose-500/40 text-rose-700 dark:text-rose-300",
};

const STATUS_LABEL: Record<UserRow["status"], string> = {
  active: "active",
  pending: "pending",
  revoked: "revoked",
};

interface UsersClientProps {
  initialUsers: UserRow[];
  /** Set when the server-side fetch failed. Non-null means: show that, invent nobody. */
  loadError?: string | null;
}

export default function UsersClient({
  initialUsers,
  loadError = null,
}: UsersClientProps) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [lastInvite, setLastInvite] = useState<InviteResponse | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [pendingInvites, setPendingInvites] = useState<InviteResponse[]>([]);
  const [copied, setCopied] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<number | string | null>(null);
  const queryClient = useQueryClient();

  async function copyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  async function handleUserUpdate(
    userId: number | string,
    body: { role?: string; status?: string },
  ) {
    setRowError(null);
    setBusyUserId(userId);
    try {
      await updateUser(userId, body);
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    } catch (exc) {
      setRowError(exc instanceof Error ? exc.message : "Update failed.");
    } finally {
      setBusyUserId(null);
    }
  }

  const users = useQuery<UserRow[]>({
    queryKey: ["admin", "users"],
    queryFn: fetchUsers,
    refetchInterval: 60_000,
    initialData: initialUsers,
    initialDataUpdatedAt: 0,
  });

  // The roster could not be read. Say that, and show nobody — an invented row on
  // this page is an account the admin will go looking for.
  const failed =
    (loadError !== null || users.isError) && (users.data?.length ?? 0) === 0;

  // Invite list refreshes alongside the user table.
  useEffect(() => {
    let active = true;
    void fetchInvites().then((rows) => {
      if (active) setPendingInvites(rows);
    });
    return () => {
      active = false;
    };
  }, [users.dataUpdatedAt]);

  const invite = useMutation({
    mutationFn: () => inviteUser({ email, role }),
    onSuccess: async (data) => {
      setLastInvite(data);
      setInviteError(null);
      setEmail("");
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      const fresh = await fetchInvites();
      setPendingInvites(fresh);
    },
    onError: (exc) => {
      setLastInvite(null);
      setInviteError(
        exc instanceof Error ? exc.message : "Could not send the invite.",
      );
    },
  });

  async function handleRevoke(inviteId: string) {
    try {
      await revokeInvite(inviteId);
      const fresh = await fetchInvites();
      setPendingInvites(fresh);
    } catch (exc) {
      setInviteError(exc instanceof Error ? exc.message : "revoke failed");
    }
  }

  return (
    <div
      data-page="admin-users"
      className="mx-auto w-full max-w-7xl px-6 py-8"
    >
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="mb-6 flex items-start justify-between"
      >
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <UsersIcon className="h-5 w-5 text-primary" />
            Users
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Who can get in, and what they can do. Inviting someone sends them an
            activation link. Making someone an <strong>Admin</strong> gives them
            full control of this console; changing the role back removes it
            immediately. The last active admin can&apos;t be removed.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-test="users-invite-open">
              <UserPlus className="mr-2 h-4 w-4" />
              Invite user
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Invite a user</DialogTitle>
              <DialogDescription>
                We create an activation link and email it. If email isn&apos;t
                set up, copy the link and send it yourself.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                data-test="users-invite-email"
              />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                data-test="users-invite-role"
                className="w-full rounded-md border border-border bg-background p-2 text-sm"
              >
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
              </select>
              {lastInvite && (
                <div
                  data-test="users-invite-success"
                  className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-200"
                >
                  Invite created:{" "}
                  <strong className="text-emerald-100">{lastInvite.email}</strong>
                  {" — "}
                  <span className="font-mono">{lastInvite.invite_id}</span>
                  {lastInvite.email_sent ? (
                    <div className="mt-1 text-emerald-200/80">
                      We emailed the activation link. It expires in 24 hours.
                    </div>
                  ) : (
                    <div className="mt-2 space-y-2">
                      <div className="text-amber-200/90">
                        {lastInvite.activation_note ||
                          "Email isn't set up, so we couldn't send this. Copy the link below and send it to the user yourself — it expires in 24 hours."}
                      </div>
                      {lastInvite.magic_url && (
                        <div className="flex items-center gap-2">
                          <input
                            readOnly
                            value={lastInvite.magic_url}
                            data-test="users-invite-magic-url"
                            onFocus={(e) => e.currentTarget.select()}
                            className="w-full rounded border border-amber-500/30 bg-background px-2 py-1 font-mono text-[11px] text-amber-100"
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-7 shrink-0 text-[11px]"
                            data-test="users-invite-copy"
                            onClick={() => void copyLink(lastInvite.magic_url!)}
                          >
                            {copied ? "Copied" : "Copy"}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {inviteError && (
                <div
                  data-test="users-invite-error"
                  className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200"
                >
                  {inviteError}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                onClick={() => invite.mutate()}
                disabled={!email || invite.isPending}
                data-test="users-invite-submit"
              >
                <Mail className="mr-2 h-4 w-4" />
                {invite.isPending ? "Sending invite…" : "Send invite"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.header>

      {pendingInvites.length > 0 && (
        <Card data-test="users-invite-list" className="mb-6 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Pending invites ({pendingInvites.length})
            </CardTitle>
            <CardDescription>
              Invites expire after 7 days. The activation link is only ever
              sent to the invited address — we store a hash of it, never the
              link itself.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {pendingInvites.map((inv) => (
                <li
                  key={inv.invite_id}
                  data-test="invite-row"
                  data-invite-id={inv.invite_id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border/50 px-3 py-2 text-xs"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="font-mono text-foreground">
                      {inv.email}
                    </span>
                    <span className="text-muted-foreground" suppressHydrationWarning>
                      {inv.role} · {inv.status}
                      {inv.expires_at
                        ? ` · ${formatDate(new Date(inv.expires_at), "en")}`
                        : ""}
                    </span>
                  </div>
                  {inv.status === "pending" && (
                    <Button
                      data-test="invite-revoke"
                      variant="outline"
                      size="sm"
                      className="h-7 text-[11px] text-rose-700 dark:text-rose-300"
                      onClick={() => void handleRevoke(inv.invite_id)}
                    >
                      <XCircle className="mr-1 h-3 w-3" />
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card className="bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Users ({users.data?.length ?? 0})
          </CardTitle>
          <CardDescription>
            Everyone with an account on this server. Revoking a user ends their
            access right away.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rowError && (
            <div
              data-test="users-row-error"
              className="mb-3 rounded-md border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200"
            >
              {rowError}
            </div>
          )}
          {failed ? (
            <div
              data-test="users-load-error"
              className="rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm"
            >
              <p className="font-medium text-amber-700 dark:text-amber-300">
                The list of users could not be read
              </p>
              <p className="mt-1 text-muted-foreground">
                {loadError ?? "The server could not be reached."} Nobody is
                listed, because a name shown here that did not come from the
                server is an account you would go looking for and never find.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => users.refetch()}
                data-test="users-retry"
              >
                Try again
              </Button>
            </div>
          ) : users.isLoading && (users.data?.length ?? 0) === 0 ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Email</th>
                  <th className="px-3 py-2 text-left">Role</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Last sign-in</th>
                  <th className="px-3 py-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(users.data ?? []).map((u) => {
                  const r = ROLE_LABELS[u.role] ?? {
                    label: u.role,
                    tone: "border-border",
                  };
                  return (
                    <tr
                      key={u.id}
                      data-test="user-row"
                      data-user-id={u.id}
                      className="border-b border-border/50"
                    >
                      <td className="px-3 py-2 font-mono text-xs">{u.email}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className={cn(r.tone)}>
                          {r.label}
                        </Badge>
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className={STATUS_TONE[u.status]}>
                          {STATUS_LABEL[u.status]}
                        </Badge>
                      </td>
                      <td
                        className="px-3 py-2 text-xs text-muted-foreground"
                        suppressHydrationWarning
                      >
                        {u.last_login
                          ? formatDateTime(new Date(u.last_login), "en")
                          : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <UserCog className="h-3 w-3 text-muted-foreground" />
                          <select
                            value={u.role}
                            disabled={busyUserId === u.id}
                            data-test="user-role-select"
                            aria-label={`Role for ${u.email}`}
                            onChange={(e) =>
                              void handleUserUpdate(u.id, { role: e.target.value })
                            }
                            className="h-7 rounded-md border border-border bg-background px-1 text-[11px] disabled:opacity-50"
                          >
                            <option value="admin">Admin</option>
                            <option value="operator">Operator</option>
                            <option value="member">Member</option>
                            <option value="viewer">Viewer</option>
                          </select>
                          {u.status === "revoked" ? (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 text-[11px] text-emerald-700 dark:text-emerald-300"
                              disabled={busyUserId === u.id}
                              data-test="user-activate"
                              onClick={() =>
                                void handleUserUpdate(u.id, { status: "active" })
                              }
                            >
                              Restore access
                            </Button>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 text-[11px] text-rose-700 dark:text-rose-300"
                              disabled={busyUserId === u.id}
                              data-test="user-revoke"
                              onClick={() =>
                                void handleUserUpdate(u.id, { status: "revoked" })
                              }
                            >
                              <XCircle className="mr-1 h-3 w-3" />
                              Revoke
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
