/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// One plan, $5 a month. Every install starts with a seven-day trial and no card.
//
// This was two cards — Solo at $29 and Team at $19 a seat, with a seat counter
// and a minimum of three. The split is gone (founder's decision, 2026-08-03):
// both plans shipped the same product, so the page was asking a buyer to make
// a decision that changed nothing except the bill.
"use client";

import CheckoutButton from "@/components/CheckoutButton";
import { BILLING_DISABLED_TITLE, BILLING_ENABLED } from "@/lib/billing-flag";
import { PRICE, TRIAL_LABEL, priceLabel } from "@/lib/pricing";

const BULLETS: readonly string[] = [
  "Chat, the agent, and 100+ tools",
  "Retrieval over your own documents and meetings",
  "Seven providers, so one outage is not your outage",
  // Was "Your keys or ours". We ship no keys — every slot in .env.example is
  // empty — so "or ours" promised something a customer would discover was
  // missing on their first prompt. What is true is better anyway: the
  // providers worth starting on cost nothing to start on.
  "Your own keys — and the good ones (Groq, Gemini, Cerebras) are free",
  "Runs on your own server — no data of yours ever reaches us",
  "Cancel any month",
];

export default function PricingTiers() {
  return (
    <main
      id="pricing-tiers"
      data-testid="pricing-tiers"
      className="border-t border-border/60 bg-background py-16"
    >
      <div className="container mx-auto px-4">
        <header className="mx-auto mb-10 max-w-2xl text-center">
          <h1 className="mb-2 text-3xl font-bold tracking-tight md:text-4xl">
            Pricing
          </h1>
          <p className="text-muted-foreground">
            {TRIAL_LABEL} free, no card. After that it is {priceLabel(PRICE)} a
            month.
          </p>
        </header>

        {!BILLING_ENABLED ? (
          <div
            role="status"
            data-testid="billing-disabled-banner"
            className="mx-auto mb-8 max-w-2xl rounded-md border border-amber-300 bg-amber-50 p-4 text-center text-sm text-amber-900"
          >
            {BILLING_DISABLED_TITLE}
          </div>
        ) : null}

        <div className="mx-auto max-w-md" data-testid="pricing-tier-grid">
          <article
            data-testid="pricing-tier-solo"
            className="flex flex-col rounded-2xl border border-primary p-6 shadow-sm ring-1 ring-primary"
          >
            <h2 className="text-lg font-semibold">ABS Studio</h2>
            <p className="mt-2 flex items-baseline gap-1">
              <span className="text-3xl font-bold">{priceLabel(PRICE)}</span>
              <span className="text-sm text-muted-foreground">/month</span>
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              The editor and the server. Everything switched on.
            </p>

            <ul className="mt-4 flex-1 space-y-2 text-sm">
              {BULLETS.map((b) => (
                <li key={b} className="flex gap-2">
                  <span aria-hidden>•</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
            <div className="mt-6">
              <CheckoutButton
                tier="solo"
                seats={1}
                variant="primary"
                className="w-full"
              >
                Subscribe
              </CheckoutButton>
            </div>
          </article>
        </div>

        <p className="mx-auto mt-8 max-w-2xl text-center text-sm text-muted-foreground">
          If a subscription ends, chat and the agent pause — and that is all.
          Your documents, meetings and keys stay on your server, readable,
          exportable and deletable, for as long as you want them there.
        </p>
      </div>
    </main>
  );
}
