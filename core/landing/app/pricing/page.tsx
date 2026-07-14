/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// /pricing renders the 4-tier purchase surface.
// Previously this route 308-redirected to /#contact, severing the
// checkout flow. The component lives at PricingTiers.tsx so legacy
// PricingPage.test.tsx (Pilot/PoC contact stub) keeps passing.
import type { Metadata } from "next";

import PricingTiers from "@/components/PricingTiers";

export const metadata: Metadata = {
  title: "Pricing — ABS Server",
  description:
    "Self-host ABS for life. Pick a tier (Lifetime, Maintenance add-on, or Team Pack) and start in minutes.",
};

export default function PricingPageRoute() {
  return <PricingTiers />;
}
