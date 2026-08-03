/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// /pricing is where someone decides to pay us. Two plans, both monthly.
//
// The description below used to advertise "Lifetime, Maintenance add-on, or
// Team Pack" — a model retired months ago and not purchasable. That string is
// what a search engine prints under the page's title, so the first thing a
// buyer read about our pricing was a product that does not exist, on the page
// whose whole job is to sell the one that does. Found 2026-08-03.
import type { Metadata } from "next";

import PricingTiers from "@/components/PricingTiers";
import { PRICE, TRIAL_LABEL } from "@/lib/pricing";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    `${TRIAL_LABEL} free, no card. Then $${PRICE} a month — one plan, every ` +
    `feature. Runs on your own server; cancel any month.`,
};

export default function PricingPageRoute() {
  return <PricingTiers />;
}
