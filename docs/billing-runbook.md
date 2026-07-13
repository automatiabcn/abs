# Stripe Billing Runbook

This document defines how to take the ABS billing stack live and what the daily
operational duties are. Audience: the operator who runs ABS billing.

---

## 1. Test Mode → Live Mode

### 1.1 Prepare the Stripe Dashboard

1. Stripe Dashboard → Developers → API keys → toggle "Live mode".
2. `Reveal live key` → copy `sk_live_...` (SHOWN ONCE — if you lose it,
   regenerate; the old key becomes invalid).
3. `Webhooks` → "+ Add endpoint" → URL `https://abs.automatiabcn.com/webhooks/stripe`
   - Events: `checkout.session.completed`, `charge.refunded`,
     `customer.subscription.deleted`
   - Copy the signing secret (`whsec_...`)

### 1.2 Write them to the vault (never to a plaintext .env)

```bash
ssh prod-server
cd /opt/abs
# Vault path as seen from inside the container, age key at /app/vault-key/age.pub
sops --age=$(cat /app/vault-key/age.pub) -e -i secrets/billing.enc.json
# An editor opens → replace the ABS_STRIPE_SECRET_KEY and ABS_STRIPE_WEBHOOK_SECRET
# values with `sk_live_...` and `whsec_...`, then save.
docker compose restart abs-backend
```

Check the boot logs:
```bash
docker compose logs abs-backend | grep -i "vault boot"
# expected: "vault boot: 2 secrets loaded into settings"
```

### 1.3 Create the live products

```bash
# Dry-run first (idempotency check):
ABS_STRIPE_SECRET_KEY=sk_live_... \
  python infra/scripts/setup_stripe_products.py --mode live --dry-run
# You should see 3 WOULD-CREATE lines.

# Then the real run:
ABS_STRIPE_SECRET_KEY=sk_live_... \
  python infra/scripts/setup_stripe_products.py --mode live
# Write the resulting ABS_PRICE_*=price_... lines into the vault.
```

Safeguard: if the script sees `--mode live` with an `sk_test_` key, or
`--mode test` with an `sk_live_` key, it exits 2 and writes an ABORT message to
stderr. A wrong key cannot create the wrong products.

### 1.4 First live test (your own card — small amount)

1. `https://abs.automatiabcn.com/` → "Buy Self-Host" with your own email.
2. Use a REAL card, not a test card (Stripe live mode does not accept test
   cards).
3. Stripe Dashboard → Payments → is the payment there?
4. The email arrives → license key.
5. Open the setup wizard → activate → turn on the `mcp_require_license` toggle →
   the MCP tools must work.

### 1.5 After the first live test

- Stripe Dashboard → the payment → "Refund payment" to reverse it ($0 net).
- Check the webhook event log:
  ```bash
  docker compose exec abs-backend python -c "
  from app.db.session import get_session_sync
  from app.db.models import WebhookEvent
  from sqlmodel import select
  with get_session_sync() as db:
      for e in db.scalars(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(10)).all():
          print(e.event_type, e.event_id, e.processed_at, e.license_jti)
  "
  ```
- Is `License.revoked_at` populated? Is `revoked_reason='stripe_refund'`?

---

## 2. Rotate the Webhook Secret

If you suspect a compromise, or you accidentally pushed it to CI:
1. Stripe Dashboard → Webhooks → the endpoint → `Roll secret`.
2. Write the new `whsec_...` to the vault (step 1.2).
3. Restart the backend.
4. Stripe Dashboard → "Send test webhook" to verify (it must return 200).

---

## 3. Manual Refund (customer request)

Done from the Stripe Dashboard:
1. Payments → the payment → "Refund payment".
2. Reason: `customer_request` | `duplicate` | `fraudulent`.
3. The webhook fires automatically → `License.revoked_at` is set.
4. The refund email is sent (template: `license_refund.html`).
5. Idempotency table: if the same `event.id` arrives again, `revoked_at` is not
   overwritten and the audit trail stays clean.

---

## 4. Dispute / Chargeback

Stripe sends an email: "A dispute was opened on your charge."
1. Dashboard → Disputes → the record.
2. Upload evidence: the license_delivery email screenshot, the customer activate
   log, the API calls they made (panel access logs).
3. Set `License.revoked_at` MANUALLY in the backend (a chargeback withholds the
   payment):
   ```python
   docker compose exec abs-backend python -c "
   from datetime import datetime, timezone
   from sqlmodel import select
   from app.db.session import get_session_sync
   from app.db.models import License
   with get_session_sync() as db:
       lic = db.scalars(select(License).where(License.customer_email=='X@Y.co')).first()
       lic.revoked_at = datetime.now(timezone.utc)
       lic.revoked_reason = 'stripe_chargeback'
       db.commit()
   "
   ```

---

## 5. Common Errors

| Error | Cause | Fix |
|---|---|---|
| `503 Stripe not configured` | env missing / vault not loaded | vault decrypt + restart |
| `400 Signature could not be verified` | wrong webhook secret | rotate the endpoint secret, update the vault |
| `502 Stripe error: rate_limited` | API rate limit | exponential backoff, retry after 30s |
| `400 Invalid payload` | Stripe SDK version mismatch | `pip install -U stripe` |
| Refund webhook never arrives | events missing from the endpoint list | Dashboard → Webhooks → add the events |
| `404 No active license` (portal) | customer used a different email | cross-check `customer_id_stripe` in the Dashboard |

---

## 6. Customer Portal

`POST /v1/billing/portal` with body `{customer_email}` returns a Stripe Customer
Portal session URL (valid for 1 hour). The customer self-serves:
- Cancel subscription
- Invoice history
- Payment method update
- Email alarm prefs

Error codes:
- `503` — Stripe key not configured.
- `404` — no active license / `customer_id_stripe` empty.
- `502` — Stripe API error (written to the logs).

---

## 7. Daily Monitoring (15 min/day)

```bash
# DB direct:
sqlite3 /app/data/abs.db "SELECT event_type, COUNT(*) FROM webhook_events GROUP BY event_type"
sqlite3 /app/data/abs.db "SELECT tier, seat_count, COUNT(*) FROM licenses WHERE revoked_at IS NULL GROUP BY tier, seat_count"
```

For a single-screen view, call the `billing_status` MCP tool from your MCP
client (Stripe products + revenue + license counts + recent events).

Abnormal patterns (alarm):
- `charge.refunded > 5%` → product/payment flow problem, customer retention.
- `License.revoked_at` averaging < 7 days → demo/onboarding problem.
- `webhook_events.error NOT NULL` → handler bug, inspect the log.
- `billing_status.recent_events` with no event in 24 hours → the site may be down.

---

## 8. Emergency Contacts

- Stripe support: dashboard → Help → Contact (live mode priority: <2 hours).
- ABS backend log path: `/var/log/abs/backend.log` (audit JSONL).
- Vault backup: `~/abs-vault-backup/age.key` (cold storage — NEVER commit it to
  git).
