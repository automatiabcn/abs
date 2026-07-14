/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Public self-signup. Posts to /v1/auth/signup; an admin activates the account.
"use client";

import { useState, type FormEvent } from "react";

type SubmitState = "idle" | "submitting" | "ok" | "error";

const SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/;

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [message, setMessage] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!SLUG_PATTERN.test(tenantSlug)) {
      setState("error");
      setMessage(
        "A workspace name is 2-32 characters: lowercase letters, digits and hyphens.",
      );
      return;
    }
    setState("submitting");
    setMessage("");
    try {
      const res = await fetch("/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, tenant_slug: tenantSlug }),
      });
      if (res.status === 201 || res.status === 200) {
        const body = await res.json().catch(() => ({}));
        setState("ok");
        // Honesty: self-signup no longer auto-emails a link. Surface the
        // backend's activation_note (guides the user to ask their admin).
        setMessage(
          body.activation_note ??
            "Your request is in. An admin on your team has to activate the account before you can sign in.",
        );
      } else {
        const body = await res.json().catch(() => ({}));
        setState("error");
        setMessage(body.detail ?? "We could not create the account. Try again in a moment.");
      }
    } catch {
      setState("error");
      setMessage("We could not reach the server. Check your connection and try again.");
    }
  };

  return (
    <main
      data-page="signup"
      className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6 py-12"
    >
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Create an account
      </h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        Your account starts out pending — an admin on your team activates it. The
        workspace name is your team&apos;s part of the URL (
        <code>{tenantSlug || "your-co"}</code>.abs.local).
      </p>

      <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-100">
            Email
          </span>
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@your-co.com"
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:ring-zinc-50"
            autoComplete="email"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-100">
            Workspace name
          </span>
          <input
            type="text"
            required
            value={tenantSlug}
            onChange={(event) => setTenantSlug(event.target.value.toLowerCase())}
            placeholder="your-co"
            // No HTML `pattern` attr: browsers compile it with the RegExp `v`
            // flag, where a literal `-` in a char class is a syntax error
            // ("Invalid character in character class"). The submit handler's
            // SLUG_PATTERN.test() + the backend already validate the slug.
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:ring-2 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:ring-zinc-50"
            autoComplete="off"
          />
        </label>
        <button
          type="submit"
          disabled={state === "submitting"}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-50 transition hover:bg-zinc-800 disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {state === "submitting" ? "Creating…" : "Create account"}
        </button>
      </form>

      {message && (
        <p
          role="status"
          data-state={state}
          className={
            "mt-4 text-sm " +
            (state === "ok"
              ? "text-emerald-600 dark:text-emerald-400"
              : state === "error"
                ? "text-rose-600 dark:text-rose-400"
                : "text-zinc-600 dark:text-zinc-300")
          }
        >
          {message}
        </p>
      )}

      {/* /login links here, and nothing linked back — someone who followed the
          signup link by mistake, or who already has an account, had no way out
          of this page but the address bar. */}
      <p className="mt-6 text-sm text-zinc-600 dark:text-zinc-300">
        Already have an account?{" "}
        <a className="underline" href="/login">
          Sign in
        </a>
      </p>
    </main>
  );
}
