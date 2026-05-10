/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// R65 (S8) — split-shell client island for /admin/users. Original
// logic from `page.tsx` lifted here verbatim; the only delta is that
// `initialUsers` from the server component seeds React Query as
// `initialData` so first paint already renders rows.
"use client";

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
}

// Sprint 2B BUG-36 — real invite endpoint. The backend persists a
// tenant_invites row, hashes the magic-link token (NEVER returned on
// the wire), and emails the recipient. The operator only sees the
// invite_id + expiry; the magic URL itself is sent via Resend/SMTP.
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

const ROLE_LABELS: Record<string, { label: string; tone: string }> = {
  admin: { label: "Admin", tone: "bg-rose-500/15 text-rose-300 border-rose-500/30" },
  operator: {
    label: "Operatör",
    tone: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  },
  viewer: {
    label: "Okur",
    tone: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  },
};

const STATUS_TONE: Record<UserRow["status"], string> = {
  active: "border-emerald-500/40 text-emerald-300",
  pending: "border-amber-500/40 text-amber-300",
  revoked: "border-rose-500/40 text-rose-300",
};

const STATUS_LABEL: Record<UserRow["status"], string> = {
  active: "aktif",
  pending: "beklemede",
  revoked: "iptal edildi",
};

interface UsersClientProps {
  initialUsers: UserRow[];
}

export default function UsersClient({ initialUsers }: UsersClientProps) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [lastInvite, setLastInvite] = useState<InviteResponse | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [pendingInvites, setPendingInvites] = useState<InviteResponse[]>([]);
  const queryClient = useQueryClient();

  const users = useQuery<UserRow[]>({
    queryKey: ["admin", "users"],
    queryFn: fetchUsers,
    refetchInterval: 60_000,
    initialData: initialUsers,
    initialDataUpdatedAt: 0,
  });

  // Sprint 2B BUG-36 — invite list refreshes alongside the user table.
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
      setInviteError(exc instanceof Error ? exc.message : "bilinmeyen hata");
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
    <main
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
            Kullanıcılar
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Magic-link davet, role atama, oturum iptali. Bootstrap admin
            tenant başına 1, ek davetler operator/viewer rollü.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-test="users-invite-open">
              <UserPlus className="mr-2 h-4 w-4" />
              Davet et
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Yeni kullanıcı davet et</DialogTitle>
              <DialogDescription>
                Magic-link oluşturulur, e-postaya gönderilir veya kopyalanır.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="kullanici@firma.com"
                data-test="users-invite-email"
              />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                data-test="users-invite-role"
                className="w-full rounded-md border border-border bg-background p-2 text-sm"
              >
                <option value="admin">Admin</option>
                <option value="member">Member</option>
              </select>
              {lastInvite && (
                <div
                  data-test="users-invite-success"
                  className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-200"
                >
                  Davet gönderildi:{" "}
                  <strong className="text-emerald-100">{lastInvite.email}</strong>
                  {" — "}
                  <span className="font-mono">{lastInvite.invite_id}</span>
                  <div className="mt-1 text-emerald-200/80">
                    Magic-link e-posta ile gönderildi (7 gün ömür). URL backend
                    log'larına yazılmaz.
                  </div>
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
                {invite.isPending ? "Davet gönderiliyor…" : "Davet gönder"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.header>

      {pendingInvites.length > 0 && (
        <Card data-test="users-invite-list" className="mb-6 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              Bekleyen davetler ({pendingInvites.length})
            </CardTitle>
            <CardDescription>
              7 gün geçerli. Magic-link plaintext'i sadece e-postaya gönderilir;
              backend HMAC digest'i tutar.
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
                    <span className="text-muted-foreground">
                      {inv.role} · {inv.status}
                      {inv.expires_at
                        ? ` · ${new Date(inv.expires_at).toLocaleDateString("tr-TR")}`
                        : ""}
                    </span>
                  </div>
                  {inv.status === "pending" && (
                    <Button
                      data-test="invite-revoke"
                      variant="outline"
                      size="sm"
                      className="h-7 text-[11px] text-rose-300"
                      onClick={() => void handleRevoke(inv.invite_id)}
                    >
                      <XCircle className="mr-1 h-3 w-3" />
                      İptal
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
            Kayıtlı kullanıcılar ({users.data?.length ?? 0})
          </CardTitle>
          <CardDescription>
            Pending davetlerin magic-link'i 7 gün geçerli; magic-link sadece
            e-postaya gönderilir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {users.isLoading && (users.data?.length ?? 0) === 0 ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">E-posta</th>
                  <th className="px-3 py-2 text-left">Rol</th>
                  <th className="px-3 py-2 text-left">Durum</th>
                  <th className="px-3 py-2 text-left">Son giriş</th>
                  <th className="px-3 py-2 text-left">Aksiyon</th>
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
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {u.last_login
                          ? new Date(u.last_login).toLocaleString("tr-TR")
                          : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-[11px]"
                            disabled
                          >
                            <UserCog className="mr-1 h-3 w-3" />
                            Rol
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-[11px] text-rose-300"
                            disabled={u.email === "admin@demo-acme.com"}
                          >
                            <XCircle className="mr-1 h-3 w-3" />
                            İptal
                          </Button>
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
    </main>
  );
}
