# Telemetry Primer — Metric Definitions

*Automatia BCN Self‑host AI Orchestration (ABS)*

---

## Revenue Metrics

### gross_mrr_usd
Monthly Recurring Revenue (MRR) before refunds and chargebacks. Computed as the sum of all active subscription billing amounts divided by billing cycle length, annualized to monthly.

**Computation:**
- **MTD (Month-to-Date):** Sum of processed charges since first day of current calendar month.
- **Today:** Charges processed in the last 24 hours (rolling window).
- **Total:** Historical cumulative sum from account creation.

### net_mrr_usd
MRR after refunds, disputed charges, and failed payment recovery. Calculated as `gross_mrr_usd - refunds_mtd - chargebacks_mtd`.

### Why estimates exist before Stripe report finalization
Stripe batches settlement reports on a 48–72 hour delay. The ABS telemetry dashboard pulls real-time transaction data via Stripe's Reporting API (`/v1/balance/transactions`), which includes *pending* and *available* funds. Estimates are flagged with a `provisional: true` field until Stripe's settlement report confirms the final amount. Operators should treat MTD/today figures as *expected* revenue subject to 1–2% variance from the final settlement.

---

## License Retention Cohorts

### Structure
Cohort analysis groups licenses by signup month and tracks how many remain active in subsequent months. The table is indexed as:

| Signup Month | M0 (signup) | M1 | M2 | M3 | M4 | M5 | M6 |
|---|---|---|---|---|---|---|---|
| 2025-12 | 47 | 45 | 42 | 40 | 38 | 37 | — |
| 2026-01 | 63 | 61 | 58 | — | — | — | — |
| 2026-02 | 89 | 86 | — | — | — | — | — |

### How it's built
- **M0:** Count of unique licenses created in that month (from `license.created_at`).
- **M1+:** Count of licenses from that cohort still in `status != revoked` and `status != expired` at the end of each subsequent month.
- Query: `SELECT signup_month, COUNT(*) FILTER (WHERE active_at >= {end_of_month}) FROM licenses GROUP BY signup_month`.

---

## Security Score

Composite health metric ranging from 0–100, derived from four sub-metrics:

### Thresholds

| Threshold | Label | Trigger |
|-----------|-------|---------|
| ≥ 80 | **ok** (green) | No active issues; all checks pass. |
| 60–79 | **warn** (amber) | One or more minor vulnerabilities; rotations overdue or trending. |
| < 60 | **danger** (red) | Critical issues: unpatched breaches, vault integrity failure, rotation >90 days. |

### What triggers each state

1. **Unset webhook secrets count** – Each missing or empty `webhook_secret` in the service config subtracts 5 points. Max penalty: 20 points.
2. **Breach count** – Number of confirmed or suspected data exposures flagged in audit logs. Each breached endpoint subtracts 15 points. Max: 30 points.
3. **Vault chain integrity** – Cryptographic verification of the sops/age vault chain. Failure = instant 25-point penalty.
4. **Last rotation age** – Days since last vault key rotation (env-tracked via `VAULT_ROTATION_DATE`). 
   - ≤ 30 days: 0 penalty
   - 31–60 days: 5 points
   - 61–90 days: 15 points
   - > 90 days: 30 points

**Example:** 2 missing webhooks (−10), 1 breach (−15), rotation 75 days old (−15) = `100 − 10 − 15 − 15 = 60` → **warn**.

---

## Churn Formula

**Heuristic flag:** A license is flagged for churn if its rolling 7-day usage average drops below 50% of its prior 30-day average.

```
avg_7d = SUM(daily_api_calls[today-6:today]) / 7
avg_30d = SUM(daily_api_calls[today-29:today]) / 30
flag_churn = (avg_7d / avg_30d) < ABS_CHURN_THRESHOLD
```

**Default threshold:** `ABS_CHURN_THRESHOLD=0.5` (50%).

**Tunable:** Operators can adjust via environment variable. Higher values (e.g., 0.6) flag more aggressively; lower (e.g., 0.3) only flag severe drops.

**Effect:** Flagged accounts appear in the admin dashboard and trigger daily CSV exports for outreach teams.

---

## Compliance Status

### States

| State | Meaning | Action |
|-------|---------|--------|
| **gap** | Missing required compliance docs or pending-deletion backlog > threshold. | Blocks deployments; ops must remediate before release. |
| **warn** | One or more compliance checks incomplete; documentation present but stale. | Warning only; releases proceed but flagged. |
| **ok** | All required docs present, current, and verified; no pending-deletion queue. | Normal operation. |

### Mapping to docs and deletion queue

- **Docs presence:** Scans for required GDPR (`privacy_policy.md`), PCI‑DSS (`pci_audit.json`), SOC2 (`soc2_report.pdf`). Missing any → **gap**.
- **Pending-deletion count:** Accounts marked for deletion but not yet purged (age > 30 days) → subtract from compliance score.
  - 0–2 pending: no impact (within grace period).
  - 3–5 pending: **warn**.
  - \> 5 pending: **gap** (backlog risk).

---

## Beta Funnel

### signups_24h
Number of new beta requests submitted in the last 24 hours. Refreshed hourly.

### conversion_rate
Percentage of beta-approved licenses that convert to paid subscription.

```
conversion_rate = approved_to_paid_count / total_approved_count * 100
```

- **Numerator:** Licenses approved via `/v1/admin/beta/{id}/approve` that later transitioned to `status=active` in the `billing.subscriptions` table.
- **Denominator:** Total approvals issued (regardless of current subscription status).

**Target:** ≥ 20% conversion. Below 15% signals product-market fit issues; above 30% indicates strong demand.

---

## When to Alert

### Rule 1: Security = danger → Discord
If `security_score < 60`, post a message to the ops Discord channel `#alerts` immediately. Include:
- Current score and threshold.
- Top 3 contributing factors (e.g., "vault rotation 102 days old").
- Recommended remediation.

### Rule 2: Churn flag count > 3 daily → Email
If the daily churn report shows > 3 flagged accounts, send an email to `ops@abs.internal` with:
- List of flagged account IDs and current usage trend.
- Suggested outreach template.

### Rule 3: Compliance = gap → Blocks releases
If `compliance_status = gap`, deployments to production are blocked. CI/CD pipeline checks this status; operators must resolve all gaps and manually bump compliance to **warn** or **ok** before release can proceed.

---

Last updated: 2026-04-27
