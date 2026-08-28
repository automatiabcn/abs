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

import { RELEASE } from "@/lib/downloads";

export const BILLING_ENABLED =
  (process.env.NEXT_PUBLIC_BILLING_ENABLED ?? "true").toLowerCase() === "true";

// One source of truth with /download. While no build is published, the
// reason is derived from RELEASE here — the env text (set on Vercel, outside
// the repo) once said "the server download are ready now" on /pricing while
// /download said "No build has been published yet" (live, 2026-08-28, #35).
// The env override applies only once a release exists and checkout is
// paused for some other reason.
export const BILLING_DISABLED_TITLE =
  RELEASE === null
    ? "Checkout opens with the first release. Nothing is published yet — the seven-day trial starts with the first build, no card needed."
    : process.env.NEXT_PUBLIC_BILLING_DISABLED_REASON ??
      "Checkout temporarily paused — please contact support.";
