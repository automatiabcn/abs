# ABS Operations

This document describes how ABS is operated: the monitoring mechanisms, the release process and the maintenance routines. The goal is to spell out the steps and the architecture that keep the system stable and reliable.

## 1. Operations Summary

ABS operations rest on a central monitoring service (Central Watchdog) plus health monitoring that runs inside each customer installation. The objectives are to detect provider changes before they break anything, to roll out system updates without disruption, and to keep serving through outages via automatic fallback and caching. In the self-hosted model the customer is responsible for backups. Support is provided over email, and later also over Discord.

## 2. Central Watchdog — Architecture and Flow

The Central Watchdog is the central monitoring and alerting service for ABS.

- **Type**: Python cron service
- **Frequency**: daily at 06:00 (UTC)
- **Hosting**: Hetzner VPS, $5-10/month
- **URL**: `abs.automatiabcn.com/watchdog/` (internal, vendor access only)
- **Providers watched**: 6 providers (Anthropic, Groq, Cerebras, CloudFlare, Gemini, Cohere)

### What is Scanned

For each provider the watchdog pulls:

- **Pricing page**: a diff of the HTML content.
- **Changelog**: RSS feeds (Anthropic, OpenAI, Groq GitHub, Gemini).
- **Status JSON**: the provider's status API (for example `status.anthropic.com/api/v2/summary.json`).
- **Synthetic test call**: a real test call against the provider's API.

### Flow

1. Every day at the scheduled time, the watchdog scans all providers.
2. If the scan turns up any change (pricing, changelog, status, or an anomaly in the synthetic test):
   - An alert fires over Discord and email.
   - Preparation of a new ABS release begins.

## 3. Update Channel — Release Process

ABS ships provider configuration and system updates through the **Update Channel**.

- **Configuration files**: `infra/provider-configs/*.yaml` in the vendor repository.
- **Contents**: model aliases, pricing metadata, health endpoints and known limits for each provider.
- **Updates**: the files in this directory are refreshed with every ABS release.
- **Customer update**: when a customer runs `docker-compose pull`, the new configuration arrives with the image.
- **Critical changes**: for changes that cannot wait, a hotfix release is published and customers are notified by email.

### How Customers Update

- **Notification**: an "Update available v1.x.y" notice appears in the ABS panel.
- **Release notes**: the notice links to the release notes.
- **Update step**: one-click update (`docker-compose pull && up -d`).
- **Breaking changes**: manual migration scripts are supplied and documented for anything backwards-incompatible.

## 4. Health Monitor in the Customer Installation

Every ABS installation runs its own health monitoring.

- **Frequency**: a synthetic call (ping) to every provider, every 60 seconds.
- **States**:
  - `ok`: the provider is working normally.
  - `degraded`: the provider is slow or partially failing.
  - `down`: the provider is unreachable.
- **Panel display**: the state is shown in the customer panel as a coloured banner (green/amber/red).
- **Automatic fallback**: when a provider goes `down`, the system moves on to the next suitable provider in the chain. The switch is silent from the user's point of view.

## 5. Circuit Breaker and Semantic Cache

ABS uses a circuit breaker and a semantic cache to stay up under provider failures.

### Circuit Breaker

- **Trigger**: 5 errors from a given provider within 1 minute puts that provider into the "open" state.
- **Reset timeout**: a provider in the "open" state receives no requests for 60 seconds. After that it moves to "half-open".
- **Half-open**: in the "half-open" state a single test request is sent to the provider.
  - If the test succeeds, the provider returns to "closed" and is fully recovered.
  - If the test fails, the provider goes back to "open" and the reset timeout starts again.
- **Logging**: every circuit breaker state change and event is written to the logs.

### Semantic Cache

- **TTL (time-to-live)**: 5 minutes.
- **Key**: the SHA-256 hash of the prompt.
- **Graceful degradation**: when a provider is broken or unreachable, the system keeps serving by returning results from the cache.

## 6. The 4-Layer Customer Guarantee

ABS offers a four-layer guarantee for service continuity:

1. **One provider goes down**: the system automatically moves to the next provider in the chain. 99% of users never notice.
2. **A provider is deprecated**: ABS absorbs this through the provider abstraction and the automatic update mechanism. The customer usually has to do nothing.
3. **A free tier is withdrawn**: a banner appears in the panel with alternative providers or workarounds.
4. **Every provider is down**: the system tries to answer from the cache. On top of that, the customer can go straight to Anthropic with their own Anthropic API key.

## 7. Weekly Operator Routine

The weekly routine that keeps ABS operationally sustainable:

- **Monday morning (30 min)**: review the Central Watchdog reports.
- **Community signals**: scan r/LocalLLaMA, Hacker News and the providers' Discord channels for emerging problems or notable changes.
- **Hotfix preparation**: prepare hotfix releases for anything found, if needed.
- **Rest of the week is automatic**: unless the watchdog raises an alert, no manual intervention is required during the week.

## 8. Logs and Monitoring

ABS collects several logs and metrics that describe the state and performance of the system:

- **Audit log**: who did what, and when.
- **Provider health log**: the health history of each provider.
- **Cache hit/miss counter**: cache hit and miss rates.
- **Workflow durability state (SQLite)**: the durability state of workflows, stored in SQLite.
- **Judge log**: the scoring history.

## 9. Backups

ABS is a self-hosted product, so backups are the customer's responsibility.

- **Data**: the default installation uses a SQLite database (`/app/data/abs.db` — organisations, users, OAuth and the audit chain) and the age-encrypted secrets file (`/app/data/secrets.yaml`).
- **Tool (backup)**: `scripts/dr/backup_sqlite.sh` — takes a **consistent** snapshot of the running database (the SQLite `.backup` API; running `tar` over the volume can capture a half-written page and produce a corrupt restore) and packs `abs.db` + `secrets.yaml` into a timestamped `.tar.gz`. It runs from inside the container or from the host (`docker compose exec backend ...`).
- **Tool (restore)**: `scripts/dr/restore_sqlite.sh <bundle>` — copies the existing database to `abs.db.pre-restore-<date>` before restoring, runs an integrity check, and refuses an unguarded restore when it detects a live database (`-wal/-shm`).
- **Vault key**: `secrets.yaml` stays encrypted; you need the age vault key to decrypt it. Back that key up **separately and securely** — storing it next to the encrypted secrets defeats the encryption.
- **Detailed runbook**: `docs/dr-runbook.md` (default SQLite installation + Postgres installation at scale).

## 10. Support Channel

The support channels available to customers:

- **Email**: `support@automatiabcn.com`
- **Paid priority support**: guaranteed response within 48 hours for maintenance subscribers.
- **Community**: a Discord channel will provide community support from Phase 2 onwards.

## 11. Watchdog Deploy (Hetzner)

The ABS Central Watchdog is a standalone cron service that runs **on the vendor side**. It scans provider pricing and changelogs once a day and posts to a Discord webhook when it detects a change. It does not run on the customer's ABS server.

### VPS Spec
- A Hetzner CX11 (~€4/month, 2 vCPU, 4 GB RAM, 40 GB SSD) is enough.
- Alternative: the smallest DigitalOcean droplet (~$6/month).

### DNS
- A record: `watchdog.automatiabcn.com → <VPS IP>` (optional, for SSH access).

### Installation
```bash
# 1) Prepare the VPS (Ubuntu 22.04+)
ssh root@<vps-ip>

# 2) Run deploy.sh (with env overrides)
DISCORD_WEBHOOK="https://discord.com/api/webhooks/..." \
INSTALL_DIR=/opt/abs-watchdog \
WATCHDOG_USER=watchdog \
bash /tmp/deploy.sh

# 3) Load the code
git clone https://github.com/automatia/abs /opt/abs-watchdog/src
# or: scp infra/watchdog/* root@vps:/opt/abs-watchdog/src/watchdog/

# 4) Test run
sudo -u watchdog bash -c "cd /opt/abs-watchdog/src && \
  WATCHDOG_DISCORD_WEBHOOK='https://...' \
  .venv/bin/python -m watchdog.cron"

# 5) Cron logs
journalctl -t abs-watchdog -f
```

`deploy.sh` does the following:
- creates the `watchdog` user (a system user)
- installs a Python venv + httpx/pyyaml
- adds the `/etc/cron.d/abs-watchdog` cron entry (06:00 UTC)
- adds `/etc/logrotate.d/abs-watchdog` for weekly rotation

### Discord Webhook Setup
1. In the Discord server: channel → Edit Channel → Integrations → Webhooks → New Webhook
2. Copy the URL (`https://discord.com/api/webhooks/<id>/<token>`)
3. Pass it as `DISCORD_WEBHOOK=<url>` when running `deploy.sh`

## 12. Manifest Release Flow

The steps required **on the vendor side** to publish a new ABS version (the private key stays secret):

```bash
# 1) Prepare the new release manifest
cat > manifest.json <<EOF
{
  "current_version": "0.2.0",
  "released_at": "2026-04-30T00:00:00Z",
  "channel": "stable",
  "min_version": "0.1.0",
  "critical": false,
  "changelog_url": "https://abs.automatiabcn.com/releases/0.2.0",
  "changelog_summary": "RAG hybrid + ML persona training",
  "docker_image": "ghcr.io/automatia/abs-backend:0.2.0",
  "breaking": false
}
EOF

# 2) Sign it (private.pem lives in 1Password — pull it out to use it)
openssl dgst -sha256 -sign manifest-keys/private.pem -out manifest.json.sig.bin manifest.json
base64 manifest.json.sig.bin > manifest.json.sig

# 3) Upload to the release server
aws s3 cp manifest.json     s3://abs-releases/manifest.json
aws s3 cp manifest.json.sig s3://abs-releases/manifest.json.sig

# 4) Test
curl https://abs.automatiabcn.com/releases/manifest.json
curl https://abs.automatiabcn.com/releases/manifest.json.sig
```

On the customer side the manifest is verified at fetch time against `app/update/manifest_pubkey.pem`. If the signature cannot be verified, the state comes back as `state="unknown"` (fail-closed). `update_signature_required=False` is for dev and test only.

### Master Key Ownership
- The **private key** (`manifest-keys/private.pem`) is the **only key** and belongs to the Automatia BCN team. Keep it in 1Password, on a hardware token, or encrypted offsite.
- Committing it to the repository is forbidden (`.gitignore` covers `manifest-keys/`).
- Losing the key means releases can no longer be signed — recovery requires a key rotation flow (generate a new key, push a new `manifest_pubkey.pem` to customers; this is a breaking update).
