# Beta Customer Onboarding Runbook (T-063)

> **Status:** scaffolding shipped. **Activating real customers requires explicit
> founder approval** (real contracts, real money, real PII). Do not proceed
> without sign-off.

## Goals

| Metric | Target |
|---|---|
| Live beta customers | 3 – 5 KOBİ (small-medium businesses) |
| Engagement | Weekly written feedback + 30-min call |
| NPS | > 30 |
| Churn during beta | 0 |
| P0 hotfix turnaround | < 48 h from report to deploy |

## Customer Profile

We're optimising for fit-for-purpose feedback, not vanity:

- 5–50 person companies that already use Claude Pro internally.
- At least one technical lead comfortable running `docker compose`.
- Workflow already touches RAG, meeting transcription, or status reporting (the three highest-value flows).
- Geo: EU first (GDPR familiarity), TR/EN/ES locales preferred.

## Stages

### Stage 0 — Pre-flight (founder)

1. Helm umbrella shipped to staging (T-058 deploy-staging green).
2. Load test ran clean (T-059 weekly cron green for 2 consecutive runs).
3. DR drill green at least once (T-062 first run recorded `rto_pass=true`).
4. Security nightly clean for 7 consecutive days (T-060).
5. Stripe still in TEST mode; live mode flips only after T-064 GA gate.

### Stage 1 — Outreach

1. Identify 8–12 candidates from the Beta waitlist (`beta_requests` table, `status=pending`).
2. Send the warm intro email (`docs/operations/templates/beta-warm-intro.md`).
3. Schedule a 20-min discovery call to confirm fit.
4. Pick the 3–5 strongest fits.

### Stage 2 — Contracting

1. Send the beta agreement (`docs/operations/templates/beta-agreement.md`) with:
   - 90-day pilot, no payment.
   - Mutual NDA.
   - Right to use anonymised case-study post-pilot.
   - Customer commits to weekly feedback + a 30-min monthly call.
2. Counter-sign + archive in customer-data-room.
3. Mark `beta_requests.status='approved'` and provision license via admin endpoint.

### Stage 3 — Onboarding (per customer)

1. Schedule kick-off call (60 min): introduce stack, show quickstart-30min.md.
2. Provision a managed sandbox (Helm release in their dedicated namespace).
3. Walk them through their first RAG query while screen-sharing.
4. Hand over the support runbook (`docs/operations/troubleshooting.md`) + Slack-Connect channel.
5. Day 7 check-in: did they get past the first week without escalation?

### Stage 4 — Operate

| Cadence | Activity |
|---|---|
| Daily | Watch LangFuse for their tenant errors (`abs-{slug}-error` Grafana alerts). |
| Weekly | 30-min written feedback form (NPS + open text). |
| Monthly | 30-min call. Capture roadmap input. |

### Stage 5 — Hotfix Process

When a beta customer files a P0:

1. Triage in 1 h. Acknowledge in writing.
2. Create branch `hotfix/p0-<short-name>`.
3. Land fix + test.
4. Run abbreviated CI (lint + test + helm-lint) — full pipeline overkill for hotfix.
5. Deploy to their namespace via `helm upgrade --reuse-values --set image.tag=hotfix-<sha>`.
6. Validate with the customer.
7. Backport to `main` after ≥ 24 h soak.

### Stage 6 — Exit (end of 90 days)

1. Joint review: did they get the value they wanted?
2. Convert: signed Self-Host Lifetime + Maintenance.
3. Or graceful off-board with data export (`POST /v1/me/data-export`).

## Templates Referenced

- `docs/operations/templates/beta-warm-intro.md`
- `docs/operations/templates/beta-agreement.md`
- `docs/operations/templates/nps-survey.md`

## Approval Required Before Going Live

Any of the following requires explicit founder sign-off recorded in this repo:

- Sending the first warm-intro email to a real human.
- Counter-signing the first beta agreement.
- Flipping a customer's tenant from `pending` → `approved`.
- Switching Stripe to live mode.

This runbook does **not** authorise any of those actions. It only describes the
process if/when the founder approves it.
