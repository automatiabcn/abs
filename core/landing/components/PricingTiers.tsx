/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Sprint 2I UAT-001 — pilot launch 4-tier pricing surface.
// Self-Host Lifetime $299 / Maintenance +$49/yr / Team-5 / Team-10.
"use client";

import CheckoutButton, { type CheckoutTier } from "@/components/CheckoutButton";
import {
  BILLING_DISABLED_TITLE,
  BILLING_ENABLED,
} from "@/lib/billing-flag";

type Tier = {
  id: CheckoutTier;
  name: string;
  price: string;
  cadence: string;
  bullets: readonly string[];
  cta: string;
  highlight?: boolean;
};

const TIERS: readonly Tier[] = [
  {
    id: "self-host",
    name: "Self-Host Lifetime",
    price: "$299",
    cadence: "one-time",
    bullets: [
      "Single-tenant self-host license",
      "Full source code access (BUSL-1.1)",
      "100+ MCP tools + 6-provider cascade",
      "Email support during onboarding",
    ],
    cta: "Buy lifetime",
  },
  {
    id: "maintenance",
    name: "Maintenance Add-on",
    price: "+$49",
    cadence: "/year",
    bullets: [
      "Quarterly security patches",
      "Priority bug fixes",
      "1-business-day support SLA",
      "Stacks on top of any Self-Host tier",
    ],
    cta: "Add maintenance",
  },
  {
    id: "team-5",
    name: "Team Pack — 5 seats",
    price: "$1,196",
    cadence: "one-time",
    bullets: [
      "5 named operator seats",
      "Shared tenant + RBAC roles",
      "Onboarding workshop (90 min)",
      "Maintenance year-1 included",
    ],
    cta: "Buy 5-seat team",
    highlight: true,
  },
  {
    id: "team-10",
    name: "Team Pack — 10 seats",
    price: "$2,093",
    cadence: "one-time",
    bullets: [
      "10 named operator seats",
      "Custom SSO mapping",
      "Onboarding workshop (half day)",
      "Maintenance year-1 included",
    ],
    cta: "Buy 10-seat team",
  },
];

export default function PricingTiers() {
  return (
    <section
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
            Self-host once, run forever — pick a tier that fits the team.
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
          className="grid gap-6 md:grid-cols-2 xl:grid-cols-4"
          data-testid="pricing-tier-grid"
        >
          {TIERS.map((tier) => (
            <article
              key={tier.id}
              data-testid={`pricing-tier-${tier.id}`}
              className={
                "flex flex-col rounded-2xl border p-6 shadow-sm " +
                (tier.highlight
                  ? "border-blue-500 ring-1 ring-blue-500"
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
                  variant={tier.highlight ? "primary" : "secondary"}
                  className="w-full"
                >
                  {tier.cta}
                </CheckoutButton>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
