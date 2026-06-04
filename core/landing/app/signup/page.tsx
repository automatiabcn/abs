/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// CJ-003 — public self-signup formu. Magic-link akisini /v1/auth/signup tetikler.
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
      setMessage("Tenant slug 2-32 karakter, sadece kucuk harf/rakam/tire.");
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
            "Kaydiniz alindi (beklemede). Hesabinizi etkinlestirmek icin yoneticinizle iletisime gecin.",
        );
      } else {
        const body = await res.json().catch(() => ({}));
        setState("error");
        setMessage(body.detail ?? "Kayit basarisiz, daha sonra tekrar dene.");
      }
    } catch {
      setState("error");
      setMessage("Aginda bir sorun olustu, internet baglantini kontrol et.");
    }
  };

  return (
    <main
      data-page="signup"
      className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6 py-12"
    >
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        ABS hesabi olustur
      </h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        Kaydin beklemede olusturulur; hesabini yoneticin etkinlestirir. Tenant
        slug, ekibinin URL kismidir (<code>{tenantSlug || "ornek-co"}</code>.abs.local).
      </p>

      <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-100">
            E-posta
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
            Tenant slug
          </span>
          <input
            type="text"
            required
            value={tenantSlug}
            onChange={(event) => setTenantSlug(event.target.value.toLowerCase())}
            placeholder="ornek-co"
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
          {state === "submitting" ? "Gonderiliyor..." : "Kayit ol"}
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
    </main>
  );
}
