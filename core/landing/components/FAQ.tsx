/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import type { FC } from "react";

interface QA {
  q: string;
  a: string;
}

const QUESTIONS: QA[] = [
  {
    q: "Does this violate Anthropic's terms of service?",
    a: "No. ABS runs on Anthropic's commercial API terms (pay-per-use). It uses a direct API key, not an OAuth token tied to a Pro subscription; Anthropic explicitly supports this usage.",
  },
  {
    q: "Does installation require technical knowledge?",
    a: "Basic Docker knowledge is enough. A single `docker compose up -d` brings ABS up in minutes (16 seconds on a warm restart, ~5-10 minutes including the first image pull). Any developer who can use SSH or a terminal will manage.",
  },
  {
    q: "What happens if I lose my license?",
    a: "The license key is stored both in the email you receive after purchase and in the ABS admin panel. If you lose it, contact support and you can get it again under your existing payment.",
  },
  {
    q: "Is there a refund guarantee?",
    a: "Yes. You can get an unconditional refund within 14 days — directly through Stripe, no questions asked. The license key is revoked after a refund.",
  },
  {
    q: "How does support work?",
    a: "Email support is standard on the base plan (support@automatiabcn.com). Customers on the maintenance package get a 48-hour response SLA.",
  },
  {
    q: "Is my code sent to Anthropic or to Automatia?",
    a: "Nothing reaches an Automatia server. ABS runs on your server and talks directly to your own Anthropic API key. On a Claude API call the request content goes to Anthropic — that is an inherent part of any Claude usage.",
  },
  {
    q: "Why ABS when Cursor / Cline / Aider exist?",
    a: "ABS is not an IDE plugin, it is a self-hosted AI network. It ships with 100+ MCP tools (120 measured), a 6-provider cascade (Anthropic, Groq, Cerebras, Gemini, CloudFlare, Cohere), quality pipelines and RAG. The founder has been building it while using it daily for 6 months.",
  },
  {
    q: "How do updates arrive?",
    a: "`docker compose pull && docker compose up -d` is all it takes. Updates come with the subscription — while it is running, you are on the current version.",
  },
  {
    q: "What happens when the trial ends, or I cancel?",
    a: "Chat and the agent pause. That is the whole of it: your documents, meetings, transcripts and provider keys stay on your server, and you can still read them, export them and delete them. Nothing is taken away, and nothing is held to ransom — the licence pauses the product, not your data. Subscribe again and it picks up where it stopped.",
  },
  // 4 new questions
  {
    q: "How does the sops/age vault protect my Anthropic API key?",
    a: "ABS uses a vault encrypted with sops + age. ANTHROPIC_API_KEY, ABS_STRIPE_SECRET_KEY and ABS_STRIPE_WEBHOOK_SECRET are always encrypted on disk; they are only decrypted into the in-memory settings object while the backend boots. The backup is the age private key file — you keep it in cold storage, and if it is lost the vault is recreated from scratch.",
  },
  {
    q: "How do refunds work, and how many days do I have?",
    a: "You can get a refund with a single click through the Stripe portal within 14 days of the purchase date. The POST /v1/billing/portal endpoint is opened by the Manage button at the top of the page; you enter your email and are sent to the Stripe Customer Portal. As soon as the refund is approved the license key is deactivated with revoked_at = now and a refund email is sent.",
  },
  {
    q: "How are GDPR and data residency handled?",
    a: "Because ABS runs on your server, all customer data stays in your jurisdiction — no user data is ever sent to Automatia BCN servers. Only the Stripe payment data (email + payment details) is processed on Stripe's infrastructure, which is PCI-DSS Level 1 certified. If a user asks, a data deletion request can be carried out from the Stripe Dashboard.",
  },
  {
    q: "Is it open source? What is the license model?",
    a: "The source is public and licensed under the Business Source License 1.1: you can read it, run it, and change it, and on the Change Date each release becomes Apache 2.0. Running it in production is what the subscription is for. A subscription — Solo, or a team by the seat — covers the whole product, updates included, for as long as it is running.",
  },
];

const FAQ: FC = () => (
  <section
    id="faq"
    aria-labelledby="faq-title"
    className="container mx-auto px-4 py-24"
  >
    <div className="mx-auto max-w-2xl text-center">
      <h2 id="faq-title" className="text-3xl font-bold tracking-tight sm:text-4xl">
        Frequently asked questions
      </h2>
    </div>

    <ul className="mx-auto mt-12 max-w-3xl space-y-4 list-none p-0">
      {QUESTIONS.map((item) => (
        <li key={item.q}>
        <details
          className="group rounded-lg border border-border bg-card p-5"
        >
          <summary className="flex cursor-pointer items-center justify-between text-base font-medium">
            <span role="term" data-testid="faq-term">{item.q}</span>
            <span
              aria-hidden="true"
              className="ml-4 text-muted-foreground transition-transform group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {item.a}
          </p>
        </details>
        </li>
      ))}
    </ul>
  </section>
);

export default FAQ;
