# Setup Guide — install ABS in 15 minutes

This guide takes Automatia ABS from nothing to a production-ready self-hosted install.
To finish in 15 minutes we use **Docker Compose**; for the manual route
(`pip install`) see the last section.

## Prerequisites

- A Linux server (Ubuntu 22.04+, Debian 12 or AlmaLinux 9 — 1 vCPU, 2 GB RAM, 20 GB disk is enough).
- Docker Engine 24+ and Docker Compose v2 (`docker compose version`).
- A DNS A record: `abs.yourcompany.com` → your server IP.
- Open ports: 80 and 443.
- An Anthropic API key (`sk-ant-...`) — [console.anthropic.com](https://console.anthropic.com/).
- A Stripe live key (`sk_live_...`) and webhook secret (`whsec_...`) — optional,
  only if you run your own payment flow.

## Step 1 — License and repository

Buy ABS at `https://abs.automatiabcn.com/` through Stripe Checkout. Keep the license
key that arrives by email; you enter it in the setup wizard at Step 4.

```bash
git clone https://github.com/automatiabcn/abs.git
cd abs/infra
cp .env.example .env
```

Fill in at least these values in `.env`:

```ini
ABS_LICENSE_KEY=eyJhbGciOiJSUzI1NiIs...   # from the email
ABS_DOMAIN=abs.yourcompany.com
ABS_ADMIN_EMAIL=admin@yourcompany.com
ABS_ADMIN_PASSWORD_BOOTSTRAP=temporary-password-for-your-first-login
```

## Step 2 — Initialise the vault (sops/age)

So that your Stripe and Anthropic secrets are never on disk in plaintext, the
**sops + age** vault is enabled (013):

```bash
# Create the age master key (ONCE — back it up; if you lose it, the vault starts over)
mkdir -p vault-key
docker run --rm -v $(pwd)/vault-key:/k alpine \
    sh -c "apk add --no-cache age && age-keygen -o /k/age.txt && cat /k/age.txt | grep public"

# copy the public key from the output → write it into .env as ABS_VAULT_AGE_PUBLIC_KEY
echo "ABS_VAULT_AGE_PUBLIC_KEY=age1xxxxx..." >> .env
```

Backup plan: copy `vault-key/age.txt` into an encrypted vault such as 1Password or Bitwarden.
If you lose it, you lose access to the encrypted secrets.

## Step 3 — Start with Docker Compose

```bash
docker compose up -d
docker compose ps
```

Three services must come up:

| Service | Port | Health |
|---|---|---|
| `backend` | 8000 (internal) | `curl localhost:8000/healthz` → 200 |
| `email-cron` | — | logs `sent=N failed=M` every 5 min |
| `caddy` | 80, 443 | automatic HTTPS via Let's Encrypt |

## Step 4 — Setup wizard (6 steps, ~5 min)

Go to `https://abs.yourcompany.com/setup`. The ABS first-run middleware sends you there automatically.

1. **Admin account** — email plus a password, stored with bcrypt.
2. **License** — the `ABS_LICENSE_KEY` from Step 1. No online check; it is an RS256-signed JWT.
3. **Domain** — the `ABS_DOMAIN` you set in the previous step (pre-filled).
4. **Anthropic API** — your `sk-ant-...` key, written to the vault encrypted.
5. **Providers** — Groq / Cerebras / Gemini / Cohere / Cloudflare API keys.
   All optional — leave one blank and the circuit breaker keeps that provider
   disabled.
6. **Test** — runs the `system_status` MCP tool; you get provider health and cache state.

When setup finishes, `setup_state.json` flips to `completed:true` and the middleware sends you to `/panel`.

## Step 5 — Connect Claude Code

Add the MCP server in Claude Code:

```bash
claude mcp add abs https://abs.yourcompany.com/mcp
```

Test it by calling the `system_status` tool from Claude Code. The expected JSON output:
100+ tools registered, 6 providers configured, vault loaded.

## Step 6 — Stripe billing (optional, for your own payment flow)

If you resell ABS to your own customers, enable the Stripe side as well:

1. `https://dashboard.stripe.com` → Developers → API keys → copy the live key.
2. Add a webhook endpoint: `https://abs.yourcompany.com/webhooks/stripe`. Events:
   `checkout.session.completed`, `charge.refunded`, `customer.subscription.deleted`.
3. Write them into the vault:
   ```bash
   sops --age=$(cat vault-key/age.pub) -e -i secrets/billing.enc.json
   # editor: ABS_STRIPE_SECRET_KEY and ABS_STRIPE_WEBHOOK_SECRET
   docker compose restart backend
   ```
4. Create the live products:
   ```bash
   ABS_STRIPE_SECRET_KEY=sk_live_... \
     python infra/scripts/setup_stripe_products.py --mode live
   ```
5. Run one live test with your own card, then refund it from the Dashboard.

Details: [Billing Runbook](billing-runbook.md).

## Step 7 — Backup and monitoring

A daily cron job is recommended:

```bash
# /etc/cron.daily/abs-backup
docker compose exec backend tar czf /tmp/abs-$(date +%F).tar.gz /app/data
mv /tmp/abs-*.tar.gz /var/backups/abs/
find /var/backups/abs -mtime +30 -delete
```

For monitoring, wire the `health_status` MCP tool into a Cloudflare Worker or
UptimeRobot — you get a Slack alert when a provider goes down.

## Step 8 — Updating

When a new version ships:

```bash
cd abs/infra
git pull
docker compose pull && docker compose up -d
docker compose logs backend | tail -50    # check the migration log
```

ABS verifies the update channel signature (014). A broken signature is rejected.

## Fresh install — clear test/QA data

The repository can carry test admins, chat history and sample RAG files created
during development and QA (for example `l24scan@test.local`, `tester-…@test.local`).
Clear them before you hand a production install over:

```bash
# 1) Dry run first — see what would be deleted
docker compose exec backend python /app/scripts/audit_test_data.py
#   → JSON output + artifacts/test_data_audit.md

# 2) Once you are happy with it, confirm
docker compose exec backend python /app/scripts/reset_test_data.py --confirm --purge-rag
```

**Automatic (first boot):** add `ABS_FRESH_INSTALL=true` to `.env` and run
`infra/scripts/first-boot-reset.sh` — the script checks the flag and skips itself
on real customer installs:

```bash
ABS_FRESH_INSTALL=true bash infra/scripts/first-boot-reset.sh
```

Rules:

- `admin@demo-acme.com` (the bootstrap admin) and `system@abs.local` are **never deleted**.
- Licenses with `tier ∈ {self-host, team, enterprise}` are **never deleted** (only `beta` ones are).
- For real customer organisation data (`demo-acme`, `default`) every deletion is
  matched per row against the email pattern; there is no organisation-wide sweep.
- A second `--confirm` run is idempotent: `total_deleted == 0`.

## Next steps

- [API Reference](api-reference.md) — 100+ MCP tools
- [Troubleshooting](troubleshooting.md) — common errors
- [FAQ](faq.md) — short answers

If you need help with the install, write to `support@automatiabcn.com` — 24h SLA for Maintenance customers.
