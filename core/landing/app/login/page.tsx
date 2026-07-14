/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Frontend login page. Posts to /auth/login (proxied through
// Next.js rewrite to FastAPI), receives the abs_session cookie, redirects
// to /panel/meetings. No client-side token handling — the cookie is
// HttpOnly and only readable by the backend.
"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { safeRedirect } from "./safeRedirect";

type LoginState = "idle" | "submitting" | "success" | "error";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Backend-unreachable banner.
  // /admin/* and /panel/* SSR layouts redirect here with this param
  // whenever the FastAPI backend /healthz probe fails.
  const backendUnreachable = searchParams?.get("reason") === "backend-unreachable";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>("idle");
  const [message, setMessage] = useState<string>("");
  // Gate the submit button until React hydrates
  // so a fast click can't trigger a native GET form submission to /login?
  // (which is what Playwright was observing — the browser
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
        // Explicit App Router push so the URL flips
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
      setMessage(`Network error: ${(exc as Error).message}`);
      setState("error");
    }
  };

  // The sign-in page was the one screen still painted in raw Tailwind zinc: a
  // black button, grey rules, no brand anywhere. Every other surface — the
  // wizard the customer just finished, the panel they are signing in to — is the
  // teal instrument theme. It is on the tokens now, so the door matches the
  // house.
  return (
    <main
      data-page="auth-login"
      className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6 py-12"
    >
      <h1 className="text-2xl font-semibold tracking-tight">
        Automatia ABS · Sign in
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Sign in with the email and password you set up in the setup wizard or
        received through a magic link.
      </p>

      {backendUnreachable && (
        <p
          role="alert"
          data-testid="backend-unreachable-banner"
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
        >
          The backend is unreachable right now. Please try again in a few minutes.
        </p>
      )}

      <form
        onSubmit={submit}
        noValidate
        data-hydrated={hydrated ? "true" : "false"}
        className="mt-6 flex flex-col gap-4"
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Email</span>
          {/* `name` as well as autoComplete: some password managers key off it,
              and without either they leave the form alone. */}
          <input
            name="email"
            type="email"
            required
            autoFocus
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@your-co.com"
            className="rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-ring/40"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Password</span>
          <input
            name="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-ring/40"
          />
        </label>
        <button
          type="submit"
          disabled={!hydrated || state === "submitting"}
          data-testid="login-submit"
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-60"
        >
          {state === "submitting" ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {state === "error" && message && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {message}
        </p>
      )}

      <p className="mt-6 text-xs text-muted-foreground">
        Don&apos;t have an account?{" "}
        <a className="underline hover:text-foreground" href="/signup">
          Sign up
        </a>{" "}
        ·{" "}
        <a className="underline hover:text-foreground" href="/auth/magic">
          Use your magic link
        </a>
      </p>
    </main>
  );
}
