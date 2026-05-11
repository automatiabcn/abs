/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q6 PB — frontend login page. Posts to /auth/login (proxied through
// Next.js rewrite to FastAPI), receives the abs_session cookie, redirects
// to /panel/meetings. No client-side token handling — the cookie is
// HttpOnly and only readable by the backend.
"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { safeRedirect } from "./safeRedirect";

type LoginState = "idle" | "submitting" | "success" | "error";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>("idle");
  const [message, setMessage] = useState<string>("");
  // FOUNDER_FIX_1 / BUG-1 — gate the submit button until React hydrates
  // so a fast click can't trigger a native GET form submission to /login?
  // (which is what Playwright + the founder were observing — the browser
  // POST never reached our handler because hydration hadn't run yet).
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    setHydrated(true);
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setState("submitting");
    setMessage("");
    try {
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) {
        // FOUNDER_FIX_1 / BUG-1 — explicit App Router push so the URL flips
        // synchronously inside the click handler (Playwright was racing the
        // old `window.location.href` assign and reading `/login`). We keep a
        // hard-nav fallback in case `router.push` is no-op (e.g., when the
        // session was already valid and the destination matches the current
        // route, App Router skips the transition).
        setState("success");
        const next = new URLSearchParams(window.location.search).get("next");
        const dest = safeRedirect(next);
        try {
          router.push(dest);
        } catch {
          /* fall through to hard-nav */
        }
        // refresh ensures any RSC layout that reads cookies (`/panel/*`)
        // re-fetches with the new abs_session.
        router.refresh();
        // belt-and-braces: hard-nav if the router did not change the URL
        // within ~150ms (lets Playwright observe the new path even when the
        // dev compile of the destination is cold).
        window.setTimeout(() => {
          if (window.location.pathname === "/login") {
            window.location.assign(dest);
          }
        }, 150);
        return;
      }
      const payload = await res.json().catch(() => ({}));
      setMessage(payload.detail ?? `HTTP ${res.status}`);
      setState("error");
    } catch (exc) {
      setMessage(`Ağ hatası: ${(exc as Error).message}`);
      setState("error");
    }
  };

  return (
    <main
      data-page="auth-login"
      className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6 py-12 text-zinc-900 dark:text-zinc-100"
    >
      <h1 className="text-2xl font-semibold">Automatia ABS · Giriş</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Setup wizard ya da magic-link ile aldığın e-posta + parolayla
        oturum aç.
      </p>

      <form
        onSubmit={submit}
        noValidate
        data-hydrated={hydrated ? "true" : "false"}
        className="mt-6 flex flex-col gap-4"
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-100">
            E-posta
          </span>
          <input
            type="email"
            required
            autoFocus
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@your-co.com"
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:ring-zinc-50"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-100">
            Parola
          </span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:ring-zinc-50"
          />
        </label>
        <button
          type="submit"
          disabled={!hydrated || state === "submitting"}
          data-testid="login-submit"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-50 transition hover:bg-zinc-800 disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {state === "submitting" ? "Giriş yapılıyor…" : "Oturum aç"}
        </button>
      </form>

      {state === "error" && message && (
        <p
          role="alert"
          className="mt-4 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-200"
        >
          {message}
        </p>
      )}

      <p className="mt-6 text-xs text-zinc-600 dark:text-zinc-400">
        Hesabın yok mu?{" "}
        <a className="underline" href="/signup">
          Yeni kayıt
        </a>{" "}
        ·{" "}
        <a className="underline" href="/auth/magic">
          Magic-link bağlantın
        </a>
      </p>
    </main>
  );
}
