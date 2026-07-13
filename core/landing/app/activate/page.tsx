/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Magic-link / invite activation page. Lives at /activate (NOT /auth/magic):
// Caddy routes /auth/* straight to the backend, so a page under /auth would
// never be served (the user would see raw JSON). It claims via
// /v1/auth/magic-claim, which the Next.js rewrite + Caddy always forward to the
// backend without the path colliding with this page.
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

type ClaimState = "idle" | "submitting" | "ok" | "expired" | "missing" | "error";

interface ClaimPayload {
  email: string;
  tenant_slug: string;
  role: string;
}

function ActivateInner() {
  const params = useSearchParams();
  const token = params?.get("token") ?? "";
  const [state, setState] = useState<ClaimState>("idle");
  const [data, setData] = useState<ClaimPayload | null>(null);
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    if (!token) {
      setState("missing");
      return;
    }
    let cancelled = false;
    setState("submitting");
    fetch(`/v1/auth/magic-claim?token=${encodeURIComponent(token)}`, {
      method: "GET",
      credentials: "include",
    })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 200) {
          const body = (await res.json()) as ClaimPayload & { status: string };
          setData(body);
          setState("ok");
        } else if (res.status === 410) {
          setState("expired");
          setMessage("This link has expired — ask your administrator for a new invite.");
        } else if (res.status === 404) {
          setState("error");
          setMessage("Token not found, or it has already been used.");
        } else {
          const detail = await res.text().catch(() => `HTTP ${res.status}`);
          setState("error");
          setMessage(`Error: ${detail.slice(0, 200)}`);
        }
      })
      .catch((exc) => {
        if (cancelled) return;
        setState("error");
        setMessage(`Network error: ${(exc as Error).message}`);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main
      data-page="activate"
      data-state={state}
      className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6 py-12 text-zinc-900 dark:text-zinc-100"
    >
      <h1 className="text-2xl font-semibold">Account verification</h1>

      {state === "submitting" && (
        <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
          Verifying your activation link…
        </p>
      )}

      {state === "missing" && (
        <p role="alert" className="mt-4 text-sm text-rose-700 dark:text-rose-300">
          Token missing. Open the activation link your administrator sent you.
        </p>
      )}

      {state === "ok" && data && (
        <section className="mt-4 rounded border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
          <p>
            Your account is active.{" "}
            <strong className="font-mono">{data.email}</strong> is now connected
            to the <strong className="font-mono">{data.tenant_slug}</strong>{" "}
            tenant.
          </p>
          <p className="mt-3">
            <a
              href="/panel"
              className="inline-block rounded bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-800"
            >
              Go to the panel →
            </a>
          </p>
        </section>
      )}

      {(state === "expired" || state === "error") && (
        <section
          role="alert"
          className="mt-4 rounded border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200"
        >
          {message || "Unknown error."}
          <p className="mt-3">
            <a
              href="/login"
              className="text-xs underline hover:text-rose-900 dark:hover:text-rose-100"
            >
              Back to sign-in
            </a>
          </p>
        </section>
      )}
    </main>
  );
}

export default function ActivatePage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-md px-6 py-12 text-zinc-500">
          Loading…
        </main>
      }
    >
      <ActivateInner />
    </Suspense>
  );
}
