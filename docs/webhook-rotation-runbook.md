# Webhook Secret Rotation Runbook

This document covers webhook signing-secret rotation for ABS's three signed
webhook surfaces: **Stripe**, **Slack** (events_api), and **GitHub App**. The
goal is zero downtime and zero replay-attack window.

> **Audience:** ABS solo operator. All commands assume `cd /opt/abs` on
> production.

---

## When to rotate

| Trigger | Urgency | Notes |
|---|:-:|---|
| Quarterly compliance schedule | Low | Plan during a low-traffic window |
| Suspected compromise (key visible in logs/Slack/git) | **P0** | Rotate immediately, audit access |
| New employee leaving with infrastructure access | High | Within 24h |
| Vendor (Stripe/Slack/GitHub) security advisory | Depends | Follow vendor instructions |

---

## 1. Stripe webhook secret

### 1.1 Rotation

```bash
# 1. Stripe Dashboard → Developers → Webhooks → endpoint detail → "Roll secret"
#    Copy the new whsec_... value.

# 2. Update vault (sops + age)
sops --age=$(cat /opt/abs/infra/vault-key/age.txt | grep public | cut -d: -f2 | tr -d ' ') \
     -e -i /opt/abs/data/secrets.yaml
# Edit ABS_STRIPE_WEBHOOK_SECRET in the editor that opens, save.

# 3. Restart backend so the new secret is loaded
docker compose restart backend

# 4. Trigger a test webhook from Stripe Dashboard ("Send test webhook")
#    Watch logs for 200:
docker compose logs backend --tail 50 | grep webhooks/stripe
```

### 1.2 Verification

- Test webhook returns 200 OK in Stripe Dashboard.
- `webhook_events` table contains a fresh row (`SELECT * FROM webhook_events ORDER BY id DESC LIMIT 5`).
- The previous secret is now rejected (manually craft a request with the old
  signature → expect 400).

### 1.3 Rollback

If the new secret rejects legitimate Stripe traffic:

1. Click "Roll secret" again in the Dashboard to issue a fresh value.
2. Repeat steps 1.1.2–1.1.4.
3. The previous (broken) secret is now invalidated; Stripe will not retry it.

---

## 2. Slack signing secret

### 2.1 Rotation

```bash
# 1. Slack App settings (api.slack.com/apps/<APP>/general) → Signing Secret →
#    "Show" → "Regenerate". Copy.

# 2. Update vault
sops --age=$(cat /opt/abs/infra/vault-key/age.txt | grep public | cut -d: -f2 | tr -d ' ') \
     -e -i /opt/abs/data/secrets.yaml
# Edit ABS_SLACK_SIGNING_SECRET, save.

# 3. Restart
docker compose restart backend

# 4. Trigger Slack URL verification (optional sanity check):
curl -X POST https://abs.your-domain.com/v1/integrations/slack/webhook \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=$(echo -n 'v0:'$(date +%s)':{"type":"url_verification","challenge":"x"}' | openssl dgst -sha256 -hmac "$(grep SLACK_SIGNING /opt/abs/data/secrets.yaml.dec | cut -d: -f2)" | cut -d' ' -f2)" \
  -d '{"type":"url_verification","challenge":"x"}'
# Expect 200 with {"challenge": "x"} or 401 if signature mismatched.
```

### 2.2 Verification

- Slack events from your workspace continue to arrive.
- Manually craft a request with the OLD signing secret → expect 401.

### 2.3 Rollback

Slack lets you regenerate at any time. Old secret invalidates immediately.

---

## 3. GitHub App webhook secret

### 3.1 Rotation

```bash
# 1. GitHub → Settings → Developer settings → GitHub Apps → <YourApp> →
#    Webhook secret → set a NEW value (long random string).

# 2. Update vault
# (same sops command as above, edit ABS_GITHUB_APP_WEBHOOK_SECRET)

# 3. Restart
docker compose restart backend

# 4. Trigger a redelivery from GitHub:
#    GitHub → Webhooks → Recent Deliveries → "Redeliver"
docker compose logs backend --tail 50 | grep github/webhook
```

### 3.2 Verification

- Recent Delivery in GitHub Dashboard shows 200 OK.
- The old signature is rejected (expect 401 if you replay an old payload).

### 3.3 Rollback

GitHub allows immediate regeneration; previous secret invalidates instantly.

---

## 4. Compromise scenario — all three at once

If you suspect a leak across multiple webhook secrets (e.g. lost laptop with
keychain access, leaked .env in screenshot), execute in this order:

1. **Block traffic** at the reverse proxy temporarily:
   ```bash
   docker compose exec caddy caddy reload --config /tmp/maintenance.Caddyfile
   ```
2. **Audit log review:**
   ```bash
   curl -fsS https://abs.your-domain.com/v1/admin/vault/audit \
     -H "Authorization: Bearer $ABS_ADMIN_TOKEN" | jq '.recent[]'
   ```
   Look for unexpected `decrypt` actions, foreign IPs, off-hours activity.
3. **Rotate ALL three secrets** following sections 1, 2, 3 above.
4. **Re-encrypt webhooks already received** during the suspected compromise
   window if necessary (forensic copy in `webhook_events.preincident` table).
5. **Customer notification** (if data exfiltration is plausible — required by
   GDPR Article 33 within 72 hours).
6. **Re-enable traffic** at the reverse proxy.
7. **Post-mortem:** file with `security@automatiabcn.com`, attach audit log
   excerpts and timeline.

### Compromise checklist

- [ ] All three webhook secrets rotated
- [ ] Vault audit chain integrity = ok
- [ ] Stripe rate of incoming refunds normal
- [ ] No unauthorized OAuth tokens (`SELECT * FROM connected_secrets`)
- [ ] Backend version pinned at known-good tag
- [ ] Customer notification drafted (template in `_agent-tasks/completed/017-*-summary.md`)

---

## 5. Periodic rotation schedule (recommended)

| Secret | Frequency | Owner | Last rotated |
|---|:-:|---|---|
| Stripe webhook | 90 days | Operator | YYYY-MM-DD |
| Slack signing | 180 days | Operator | YYYY-MM-DD |
| GitHub App webhook | 180 days | Operator | YYYY-MM-DD |
| Age master key | 365 days | Operator | YYYY-MM-DD |
| HMAC audit secret | 365 days (with reseal) | Operator | YYYY-MM-DD |

Track in your password manager or 1Password notes.

---

## 6. Useful one-liners

```bash
# Check the most recent webhook event per type
sqlite3 /opt/abs/data/abs.db \
    "SELECT event_type, MAX(received_at) FROM webhook_events GROUP BY event_type"

# Verify vault audit integrity
docker compose exec backend python -c \
    "from app.vault.audit_chain import verify_chain; print(verify_chain())"

# Show how many seconds since last rotation
docker compose exec backend python -c \
    "from app.vault.audit_chain import stats; \
     import datetime; \
     s = stats(window_hours=99999); \
     last = next((e for e in s['recent'] if e['action']=='rotate'), None); \
     print('last rotate:', last)"
```

For incidents not covered above, contact `security@automatiabcn.com` and file
a private GitHub security advisory.
