"use client";
/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */


import { useState, type FormEvent } from "react";

type SubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "ok"; autoApproved: boolean; licenseJti?: string }
  | { status: "error"; error: string };

const ENDPOINT = "/v1/beta/request";

export default function BetaRequestForm() {
  const [state, setState] = useState<SubmitState>({ status: "idle" });
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [useCase, setUseCase] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [lang, setLang] = useState<"en" | "tr" | "es">("en");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setState({ status: "submitting" });
    if (!email.includes("@")) {
      setState({ status: "error", error: "Email looks invalid" });
      return;
    }
    try {
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name, company, use_case: useCase, lang, website }),
      });
      if (!r.ok) {
        const body = (await r.json().catch(() => ({}))) as { detail?: string };
        const msg =
          r.status === 429
            ? "We already received a request from this email — try again tomorrow."
            : body.detail || `Request failed (${r.status})`;
        setState({ status: "error", error: msg });
        return;
      }
      const body = (await r.json()) as {
        auto_approved?: boolean;
        license_jti?: string;
      };
      setState({
        status: "ok",
        autoApproved: !!body.auto_approved,
        licenseJti: body.license_jti,
      });
    } catch (err) {
      setState({ status: "error", error: (err as Error).message });
    }
  }

  if (state.status === "ok") {
    return (
      <div data-testid="beta-confirmation" className="rounded-lg border p-6">
        <h2 className="text-lg font-semibold">
          {state.autoApproved ? "You are in" : "Request received"}
        </h2>
        <p className="mt-2 text-sm">
          {state.autoApproved
            ? "Your beta license has been issued. Check your email for setup instructions."
            : "We'll review your request and email you within 48 hours."}
        </p>
      </div>
    );
  }

  return (
    <form
      data-testid="beta-request-form"
      onSubmit={onSubmit}
      className="space-y-4 rounded-lg border p-6"
      noValidate
    >
      <div>
        <label className="block text-sm font-medium" htmlFor="beta-email">
          Email *
        </label>
        <input
          id="beta-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-sm font-medium" htmlFor="beta-name">
          Name
        </label>
        <input
          id="beta-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-sm font-medium" htmlFor="beta-company">
          Company
        </label>
        <input
          id="beta-company"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-sm font-medium" htmlFor="beta-use-case">
          Use case
        </label>
        <textarea
          id="beta-use-case"
          rows={3}
          value={useCase}
          onChange={(e) => setUseCase(e.target.value)}
          className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400"
        />
      </div>
      <div>
        <label className="block text-sm font-medium" htmlFor="beta-lang">
          Preferred language
        </label>
        <select
          id="beta-lang"
          value={lang}
          onChange={(e) => setLang(e.target.value as "en" | "tr" | "es")}
          className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400"
        >
          <option value="en">English</option>
          <option value="tr">Turkish</option>
          <option value="es">Spanish</option>
        </select>
      </div>
      {/* Honeypot — visually hidden; bots fill it. */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-9999px" }}>
        <label htmlFor="beta-website">Website</label>
        <input
          id="beta-website"
          tabIndex={-1}
          autoComplete="off"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
      </div>
      <button
        type="submit"
        disabled={state.status === "submitting"}
        className="rounded-md bg-blue-700 px-4 py-2 font-medium text-white disabled:opacity-50"
      >
        {state.status === "submitting" ? "Submitting…" : "Request beta access"}
      </button>
      {state.status === "error" && (
        <p data-testid="beta-error" className="text-sm text-red-600">
          {state.error}
        </p>
      )}
    </form>
  );
}
