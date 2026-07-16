/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// /admin/account — Account & privacy.
//
// The GDPR/KVKK self-service rights had a real backend for weeks (data export
// Art. 15, consent ledger Art. 7, personal audit log Art. 15, erasure Art. 17)
// but no operator-facing surface — the only page under /panel/account was the
// deletion-status banner, reachable only from the confirmation email. This is
// that surface: every right in one place, each wired to /v1/me/*, nothing
// invented when the server can't be reached.
//
// Auth: these endpoints take a Bearer license token OR — on a self-host box —
// the signed-in operator's panel session (app/api/me_auth.py). So a plain
// same-origin fetch with the session cookie reaches them; no token handling in
// the browser. Erasure still needs the separate email-confirm link, so this
// page can *request* a deletion but a session alone can never complete one.
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Download,
  FileArchive,
  Loader2,
  ShieldCheck,
} from "lucide-react";

// ── contracts (mirror app/api/me_*.py) ─────────────────────────────────
type Consent = {
  consent_type: string;
  version: string;
  granted_at: string | null;
  withdrawn_at: string | null;
  source: string;
  active: boolean;
};
type AuditEntry = {
  id: number;
  ts: string;
  action: string;
  resource: string | null;
  detail: string | null;
};
type DeletionStatus = {
  status: "none" | "scheduled" | "purged";
  scheduled_delete_at: string | null;
  purged_at?: string | null;
  days_remaining?: number;
};
type ExportJob = { job_id: string; status: string; expires_at: string | null };

// The consent ledger's five types, split into what the operator actually acts
// on (communication) versus the legal acceptances captured at setup.
const COMMS = [
  { key: "marketing_email", label: "Marketing emails", hint: "Product news, offers." },
  { key: "product_updates_email", label: "Product update emails", hint: "Release notes, changelog." },
];
const LEGAL: Record<string, string> = {
  tos: "Terms of Service",
  privacy: "Privacy Policy",
  dpa: "Data Processing Agreement",
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: "include", cache: "no-store", ...init });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? `The server answered ${res.status}.`);
  }
  return (await res.json()) as T;
}

// ── section shell ──────────────────────────────────────────────────────
function Section({
  title,
  law,
  children,
}: {
  title: string;
  law: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          {law}
        </span>
      </div>
      {children}
    </section>
  );
}

export default function AccountPrivacyPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Account &amp; privacy
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Export your data, manage what you&apos;ve agreed to, see every action
          taken on your account, and — if you need to — close it. These are your
          data-protection rights, wired to this server, not a form that emails
          someone.
        </p>
      </header>
      <div className="space-y-5">
        <ConsentsSection />
        <ExportSection />
        <ActivitySection />
        <DangerSection />
      </div>
    </div>
  );
}

// ── 1. Consents ─────────────────────────────────────────────────────────
function ConsentsSection() {
  const [rows, setRows] = useState<Consent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const load = useCallback(() => {
    j<{ consents: Consent[] }>("/v1/me/consents")
      .then((d) => setRows(d.consents))
      .catch((e) => setError(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  const byType = (t: string) => rows?.find((r) => r.consent_type === t);

  async function toggle(type: string, on: boolean) {
    setPending(type);
    setError(null);
    try {
      if (on) {
        await j(`/v1/me/consents`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ consent_type: type, version: "1.0" }),
        });
      } else {
        await j(`/v1/me/consents/${type}`, { method: "DELETE" });
      }
      load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setPending(null);
    }
  }

  return (
    <Section title="Consents" law="GDPR Art. 7">
      {error && <ErrorLine msg={error} />}
      {!rows && !error && <Skeleton />}
      {rows && (
        <div className="space-y-5">
          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              Communication preferences
            </div>
            <div className="space-y-2">
              {COMMS.map((c) => {
                const row = byType(c.key);
                const on = !!row?.active;
                return (
                  <div
                    key={c.key}
                    className="flex items-center justify-between gap-4 rounded-lg border border-border/60 px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-foreground">{c.label}</div>
                      <div className="text-xs text-muted-foreground">{c.hint}</div>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={on}
                      aria-label={c.label}
                      disabled={pending === c.key}
                      onClick={() => toggle(c.key, !on)}
                      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
                        on ? "bg-primary" : "bg-muted"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                          on ? "translate-x-[22px]" : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              Legal agreements
            </div>
            <div className="space-y-1.5">
              {Object.entries(LEGAL).map(([key, label]) => {
                const row = byType(key);
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-foreground">{label}</span>
                    {row?.active ? (
                      <span className="inline-flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Accepted v{row.version} · {fmt(row.granted_at)}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">Not recorded</span>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Withdrawing a legal agreement can suspend the service. Contact
              support if you need to revisit these.
            </p>
          </div>
        </div>
      )}
    </Section>
  );
}

// ── 2. Data export ───────────────────────────────────────────────────────
function ExportSection() {
  const [job, setJob] = useState<ExportJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      const res = await j<ExportJob>("/v1/me/data-export", { method: "POST" });
      setJob(res);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  const ready = job && job.status === "done";

  return (
    <Section title="Your data" law="GDPR Art. 15">
      <p className="mb-3 text-sm text-muted-foreground">
        Build an encrypted archive of everything this server holds about your
        account — profile, consents, usage and activity. The download link works
        for a limited time.
      </p>
      {error && <ErrorLine msg={error} />}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={prepare}
          disabled={busy}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />}
          {busy ? "Preparing…" : job ? "Rebuild export" : "Prepare data export"}
        </button>
        {ready && (
          <a
            href={`/v1/me/data-export/${job.job_id}/download`}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
          >
            <Download className="h-4 w-4" />
            Download archive
          </a>
        )}
      </div>
      {job && (
        <div className="mt-3 text-xs text-muted-foreground">
          {ready
            ? `Ready${job.expires_at ? ` · link expires ${fmt(job.expires_at)}` : ""}.`
            : `Export ${job.status}.`}
        </div>
      )}
    </Section>
  );
}

// ── 3. Personal activity log ─────────────────────────────────────────────
function ActivitySection() {
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    j<{ entries: AuditEntry[] }>("/v1/me/audit-log")
      .then((d) => setRows(d.entries))
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <Section title="Account activity" law="GDPR Art. 15">
      <p className="mb-3 text-sm text-muted-foreground">
        Every action recorded against your account in the last 90 days. This is
        the same record your data export includes.
      </p>
      {error && <ErrorLine msg={error} />}
      {!rows && !error && <Skeleton />}
      {rows && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">No activity recorded yet.</p>
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-2 pr-4 font-medium">When</th>
                <th className="py-2 pr-4 font-medium">Action</th>
                <th className="py-2 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border/50 last:border-0">
                  <td className="whitespace-nowrap py-2 pr-4 font-mono text-xs text-muted-foreground">
                    {fmt(r.ts)}
                  </td>
                  <td className="py-2 pr-4">
                    <span className="font-mono text-xs text-foreground">{r.action}</span>
                    {r.resource && (
                      <span className="ml-1 text-xs text-muted-foreground">· {r.resource}</span>
                    )}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">{r.detail ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

// ── 4. Delete account (danger zone) ──────────────────────────────────────
function DangerSection() {
  const [status, setStatus] = useState<DeletionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Dev/test only: the backend returns the confirm token in the body when
  // env != prod so the flow is testable without an SMTP capture. In prod it is
  // emailed and never appears here.
  const [devToken, setDevToken] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  // Trial / keyless self-host has no license record to erase yet — the backend
  // answers 404 there. That's not an error to show the operator; it means
  // deletion doesn't apply until they hold a license.
  const [noAccountRecord, setNoAccountRecord] = useState(false);

  const load = useCallback(() => {
    j<DeletionStatus>("/v1/me/account/deletion-status")
      .then((s) => {
        setStatus(s);
        setNoAccountRecord(false);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          // No license record yet (trial) — not an error to surface.
          setNoAccountRecord(true);
          setError(null);
        } else {
          setError(String(e.message ?? e));
        }
      });
  }, []);
  useEffect(load, [load]);

  async function request() {
    setBusy(true);
    setError(null);
    try {
      const res = await j<{ confirm_token?: string }>(
        "/v1/me/account/delete-request",
        { method: "POST" },
      );
      setRequested(true);
      if (res.confirm_token) setDevToken(res.confirm_token);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDev() {
    if (!devToken) return;
    setBusy(true);
    setError(null);
    try {
      await j("/v1/me/account/delete-confirm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: devToken }),
      });
      setDevToken(null);
      setRequested(false);
      load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await j("/v1/me/account/delete-cancel", { method: "POST" });
      load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  const scheduled = status?.status === "scheduled";
  const purged = status?.status === "purged";

  return (
    <section className="rounded-xl border border-rose-300 bg-rose-50/50 p-5 dark:border-rose-900 dark:bg-rose-950/30">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="flex items-center gap-2 text-base font-semibold text-rose-800 dark:text-rose-200">
          <AlertTriangle className="h-4 w-4" />
          Delete account
        </h2>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-rose-700/70 dark:text-rose-300/70">
          GDPR Art. 17
        </span>
      </div>

      {error && <ErrorLine msg={error} />}

      {noAccountRecord ? (
        <p className="text-sm text-rose-800/90 dark:text-rose-200/90">
          You&apos;re on a trial, so there&apos;s no license account on record to
          erase yet. Account deletion becomes available once you activate a
          license — your trial data is simply removed when the trial ends.
        </p>
      ) : purged ? (
        <p className="text-sm text-rose-800 dark:text-rose-200">
          This account has been purged{status?.purged_at ? ` on ${fmt(status.purged_at)}` : ""}.
        </p>
      ) : scheduled ? (
        <div className="space-y-3">
          <p className="text-sm text-rose-800 dark:text-rose-200">
            Deletion is scheduled for{" "}
            <span className="font-medium">{fmt(status!.scheduled_delete_at)}</span>
            {typeof status!.days_remaining === "number" && (
              <> — {status!.days_remaining} day{status!.days_remaining === 1 ? "" : "s"} left to change your mind.</>
            )}{" "}
            Your data is erased permanently after that.
          </p>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-rose-400 bg-background px-4 text-sm font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-50 dark:text-rose-200 dark:hover:bg-rose-900/40"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Keep my account — cancel deletion
          </button>
        </div>
      ) : requested ? (
        <div className="space-y-3">
          <p className="text-sm text-rose-800 dark:text-rose-200">
            Check your email for a confirmation link — deletion isn&apos;t
            scheduled until you click it, and the link expires in 24 hours.
          </p>
          {devToken && (
            <div className="rounded-md border border-dashed border-rose-400 p-3">
              <p className="mb-2 text-[11px] text-rose-700/80 dark:text-rose-300/80">
                Dev/test server: no email is sent, so confirm here instead.
              </p>
              <button
                type="button"
                onClick={confirmDev}
                disabled={busy}
                className="inline-flex h-8 items-center gap-2 rounded-md bg-rose-600 px-3 text-xs font-medium text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                Confirm deletion (dev)
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-rose-800/90 dark:text-rose-200/90">
            This starts a two-step erasure. We email you a confirmation link;
            once you confirm, your account is scheduled for permanent deletion
            after a 30-day grace period, during which you can still cancel.
          </p>
          <button
            type="button"
            onClick={request}
            disabled={busy}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-rose-600 px-4 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertTriangle className="h-4 w-4" />}
            Request account deletion
          </button>
        </div>
      )}
    </section>
  );
}

// ── shared bits ──────────────────────────────────────────────────────────
function ErrorLine({ msg }: { msg: string }) {
  return (
    <p
      role="alert"
      className="mb-3 rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
    >
      {msg}
    </p>
  );
}

function Skeleton() {
  return <div className="h-20 w-full animate-pulse rounded-md bg-muted/40" />;
}
