/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Single source of truth for the billing kill-switch.
// Pilot launch flips the default ON; operators may
// opt out with `NEXT_PUBLIC_BILLING_ENABLED=false`. The optional
// `NEXT_PUBLIC_BILLING_DISABLED_REASON` env var overrides the
// disabled-banner copy when a kill-switch is in effect (e.g. while a
// Stripe key rotation is in flight).

export const BILLING_ENABLED =
  (process.env.NEXT_PUBLIC_BILLING_ENABLED ?? "true").toLowerCase() === "true";

export const BILLING_DISABLED_TITLE =
  process.env.NEXT_PUBLIC_BILLING_DISABLED_REASON ??
  "Checkout temporarily paused — please contact support.";
