/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The product is a monthly subscription: Solo, or a team priced per seat.
// Every install starts with a seven-day trial and no card.
"use client";

import * as React from "react";

import CheckoutButton, { type CheckoutTier } from "@/components/CheckoutButton";
import { BILLING_DISABLED_TITLE, BILLING_ENABLED } from "@/lib/billing-flag";

export const MIN_TEAM_SEATS = 3;
export const TEAM_SEAT_PRICE = 19;

type Tier = {
  id: CheckoutTier;
  name: string;
  price: string;
  cadence: string;
  blurb: string;
  bullets: readonly string[];
  cta: string;
  highlight?: boolean;
};

const TIERS: readonly Tier[] = [
  {
    id: "solo",
    name: "Solo",
    price: "$29",
    cadence: "/month",
    blurb: "One person, one server, everything switched on.",
    bullets: [
      "Chat, the agent, and 100+ tools",
      "Retrieval over your own documents and meetings",
      "Six providers, so one outage is not your outage",
      "Your keys or ours — the free defaults are the good ones",
      "Cancel any month",
    ],
    cta: "Subscribe",
  },
  {
    id: "team",
    name: "Team",
    price: `$${TEAM_SEAT_PRICE}`,
    cadence: "/seat/month",
    blurb: `Everything in Solo, for each person. From ${MIN_TEAM_SEATS} seats.`,
    bullets: [
      "Named seats — add or remove them any month",
      "Shared workspace with roles and permissions",
      "Admin panel: who did what, and when",
      "One server, one bill, one set of documents",
      "Cancel any month",
    ],
    cta: "Subscribe",
    highlight: true,
  },
];

function clampSeats(n: number): number {
  if (!Number.isFinite(n)) return MIN_TEAM_SEATS;
  return Math.max(MIN_TEAM_SEATS, Math.min(500, Math.floor(n)));
}

export default function PricingTiers() {
  // The typed text and the number are kept apart on purpose. Clamping on every
  // keystroke means someone who selects "3" and types "5" ends up with 35 — the
  // field fights them as they type. It settles when they leave it.
  const [draft, setDraft] = React.useState(String(MIN_TEAM_SEATS));
  const seats = clampSeats(Number(draft));

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
            Seven days free, no card. After that it is $29 a month for one
            person, or ${TEAM_SEAT_PRICE} per seat for a team.
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

        <div
          className="mx-auto grid max-w-4xl gap-6 md:grid-cols-2"
          data-testid="pricing-tier-grid"
        >
          {TIERS.map((tier) => (
            <article
              key={tier.id}
              data-testid={`pricing-tier-${tier.id}`}
              className={
                "flex flex-col rounded-2xl border p-6 shadow-sm " +
                (tier.highlight
                  ? "border-primary ring-1 ring-primary"
                  : "border-border/60")
              }
            >
              <h2 className="text-lg font-semibold">{tier.name}</h2>
              <p className="mt-2 flex items-baseline gap-1">
                <span className="text-3xl font-bold">{tier.price}</span>
                <span className="text-sm text-muted-foreground">
                  {tier.cadence}
                </span>
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{tier.blurb}</p>

              {tier.id === "team" ? (
                <label className="mt-4 flex items-center gap-3 text-sm">
                  <span className="text-muted-foreground">Seats</span>
                  <input
                    type="number"
                    min={MIN_TEAM_SEATS}
                    max={500}
                    value={draft}
                    data-test="team-seats"
                    onChange={(e) => setDraft(e.target.value)}
                    onBlur={() => setDraft(String(clampSeats(Number(draft))))}
                    className="h-9 w-20 rounded-md border border-input bg-transparent px-2"
                  />
                  <span
                    data-test="team-total"
                    className="text-muted-foreground"
                  >
                    ${seats * TEAM_SEAT_PRICE}/month
                  </span>
                </label>
              ) : null}

              <ul className="mt-4 flex-1 space-y-2 text-sm">
                {tier.bullets.map((b) => (
                  <li key={b} className="flex gap-2">
                    <span aria-hidden>•</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-6">
                <CheckoutButton
                  tier={tier.id}
                  seats={tier.id === "team" ? seats : 1}
                  variant={tier.highlight ? "primary" : "secondary"}
                  className="w-full"
                >
                  {tier.cta}
                </CheckoutButton>
              </div>
            </article>
          ))}
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
