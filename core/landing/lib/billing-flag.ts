// T-R03 fix #1 — single source of truth for the billing kill-switch.
// `NEXT_PUBLIC_BILLING_ENABLED=true` lights up Buy / Subscribe / Waitlist
// flows. Default is OFF so a clean checkout doesn't ship before T-R08
// real-beta E2E + Stripe sandbox approval.

export const BILLING_ENABLED =
  (process.env.NEXT_PUBLIC_BILLING_ENABLED ?? "").toLowerCase() === "true";

export const BILLING_DISABLED_TITLE =
  "Sprint 19'da aktif — beta onboarding sonrası açılır";
