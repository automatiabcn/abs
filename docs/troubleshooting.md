# Troubleshooting

Common errors you will hit while installing or running ABS, and how to fix them.

## Landing routes 404 after adding a new page

**Symptom:** `/pricing`, `/beta`, etc. return 404 in `next dev` even though `app/<route>/page.tsx` exists.

**Cause:** stale `.next/` build cache after a new App Router page is added.

**Fix:**

```bash
cd core/landing
rm -rf .next
npx next dev
```

**Verification:** `npm run test:e2e` (Playwright suite at `__tests__/playwright/routes.spec.ts`) probes every public route for status 200 and no console errors.

## Vault / sops

### `vault disabled (binary or master key missing)`

**Cause:** the `sops` or `age` binaries are missing inside the container, or
`/app/vault-key/age.txt` is not mounted.

**Fix:**
```bash
docker compose exec backend which sops age   # both must resolve
ls -la vault-key/age.txt                     # does the file exist on the host?
docker compose down && docker compose up -d  # remount
```

`age.txt` must contain the `# created: ...` and `AGE-SECRET-KEY-1...` lines.

### `sops: failed to decrypt`

**Cause:** the secret was encrypted with a different public key than the age
public key in `.env` (`ABS_VAULT_AGE_PUBLIC_KEY`).

**Fix:** get the correct public key out of `vault-key/age.txt`
(`grep public-key vault-key/age.txt`). Update `.env` and restart.

## Stripe webhook

### `400 Stripe-Signature header missing`

**Cause:** the request to the webhook endpoint came from some client other than Stripe.

**Fix:** Stripe Dashboard → Webhooks → confirm the endpoint URL is `/webhooks/stripe`.
Send a test webhook.

### `400 Signature verification failed`

**Cause:** `ABS_STRIPE_WEBHOOK_SECRET` is wrong. The secret may have changed when
you switched to live mode.

**Fix:** Stripe Dashboard → Webhooks → endpoint detail → `Roll secret`, or reveal
the current one → write it into the vault → restart the backend.

### Refund webhooks never arrive

**Cause:** `charge.refunded` is not in the endpoint's event list in
Stripe Dashboard → Webhooks.

**Fix:** endpoint detail → Add events → select `charge.refunded` +
`customer.subscription.deleted`. Send a test webhook.

## MCP / Claude Code

### `[LICENSE REQUIRED] ABS currently requires a license`

**Cause:** `ABS_MCP_REQUIRE_LICENSE=true` but there is no licence, or the demo period expired.

**Fix:** open the setup wizard and activate a licence. To extend the demo, delete
`/app/data/demo_state.json` and restart (a fresh 14 days starts).

### `MCP tool not found: ask_xyz`

**Cause:** the tool is not in the registry. Your version may be out of date.

**Fix:**
```bash
docker compose exec backend python -c \
  "from app.mcp.server import mcp_server; import asyncio; \
   tools = asyncio.run(mcp_server.list_tools()); \
   print(sorted(t.name for t in tools))" | grep ask_xyz
```

If the output is empty, run `git pull && docker compose pull && docker compose up -d`.

### Claude Code will not connect to MCP

**Cause:** the `/mcp` path is missing from the URL, or the URL is not HTTPS.

**Fix:**
```bash
claude mcp remove abs
claude mcp add abs https://abs.yourcompany.com/mcp
claude mcp list   # status must be: connected
```

## Provider errors

### `circuit_breaker_open: anthropic`

**Cause:** the Anthropic API returned 5 consecutive errors within the last 5 minutes,
so the provider chain opened its breaker.

**Fix:**
```bash
ask "breaker_status" gptoss   # inspect the state
# manual reset:
docker compose exec backend python -c \
  "from app.cascade.breaker import reset_breaker; reset_breaker('anthropic')"
```

Check the Anthropic status page: `status.anthropic.com`.

### `rate_limited: groq`

**Cause:** you hit the Groq free tier rate limit (6000 TPM).

**Fix:** use a single-shot call such as `kimi` or `gptoss` instead of parallel
pipelines like `qual-code` / `race`. Or upgrade to the Groq Dev Tier.

### Email is not being sent

**Cause:** `ABS_SMTP_HOST` is empty — the console fallback is active (it only writes to the logs).

**Fix:** configure a real SMTP server:
```ini
ABS_SMTP_HOST=smtp.resend.com
ABS_SMTP_PORT=587
ABS_SMTP_USER=resend
ABS_SMTP_PASSWORD=re_xxxxxxxx
ABS_SMTP_FROM=noreply@yourcompany.com
```

Watch the tick output with `docker compose logs email-cron | tail -20`.

## Database

### `sqlite3.OperationalError: database is locked`

**Cause:** two processes wrote to the SQLite WAL at the same time (rare, usually a
cron job colliding with a manual query).

**Fix:** it normally clears in 1-2 seconds. If it persists:
```bash
docker compose exec backend sqlite3 /app/data/abs.db "PRAGMA journal_mode=WAL;"
```

### `no such table: webhook_events`

**Cause:** the migration did not run at boot (upgrade from a very old version).

**Fix:**
```bash
docker compose exec backend python -c \
  "from app.db.session import init_db; init_db()"
```

## Setup Wizard

### Setup stopped halfway, the panel will not open

**Cause:** the first-run middleware is active and `setup_state.json` still has `completed:false`.

**Fix:** go to `/setup` and continue where you left off. Or do it manually:
```bash
docker compose exec backend python -c \
  "import json, time, pathlib; \
   p = pathlib.Path('/app/data/setup_state.json'); \
   p.write_text(json.dumps({'completed':True,'current_step':6,'completed_steps':['admin','license','domain','anthropic','providers','test'],'started_at':time.time(),'completed_at':time.time(),'data':{}}))"
```

## Cerbos / Helm

### `helm upgrade abs` puts the Cerbos pod into CrashLoopBackOff

**Cause:** `infra/helm/abs/values*.yaml` may carry fields that Cerbos does not accept
on your Kubernetes version (`policy_compile_failed`). The current
`values.production.yaml` closes this off.

**Fix:**

```bash
cd infra/helm/abs
helm upgrade --install abs . \
    --namespace abs-prod \
    --values values.production.yaml \
    --atomic --timeout 5m
```

**Verification:**

1. `kubectl -n abs-prod rollout status deployment/abs-cerbos`
2. `kubectl -n abs-prod logs deployment/abs-cerbos --tail 50` — `policy_compile_failed` must not appear
3. `kubectl -n abs-prod exec deployment/abs-api -- curl -s localhost:3592/_cerbos/healthz` → `{"status":"SERVING"}`
4. `kubectl -n abs-prod exec deployment/abs-api -- curl -s localhost:3592/api/check` with a sample policy request → 200

## Unknown errors

Send the output of `docker compose logs backend | tail -100` to
`support@automatiabcn.com`. Maintenance customers get a response within 24h;
everyone else within 48h.

Other resources you may need:

- [FAQ](faq.md) — short answers
- [Setup Guide](setup-guide.md) — installation from scratch
- [API Reference](api-reference.md) — the MCP tool list
