# ABS Central Watchdog

A cron service run by Automatia BCN — it scans provider pricing/changelog changes once a day and posts to a Discord webhook when it detects a change.

**No impact on the customer side** — this service does not run in the backend container and is not part of the ABS server.

## Deploy (VPS, ~$5-10/month)

```bash
# 1. SSH into the VPS
ssh root@watchdog.automatiabcn.com

# 2. Copy the repo (only infra/watchdog/)
mkdir -p /opt/abs-watchdog
rsync -avz infra/watchdog/ root@watchdog.automatiabcn.com:/opt/abs-watchdog/watchdog/

# 3. Python venv + dependencies
cd /opt/abs-watchdog
python3 -m venv .venv
.venv/bin/pip install httpx pyyaml

# 4. Discord webhook env (systemd EnvironmentFile, or straight into crontab)
echo 'WATCHDOG_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...' > /etc/abs-watchdog.env

# 5. crontab
crontab -e
# Add:
# 0 6 * * * cd /opt/abs-watchdog && set -a && . /etc/abs-watchdog.env && set +a && .venv/bin/python -m watchdog.cron >> /var/log/abs-watchdog.log 2>&1
```

## MVP scope

- ✅ Skeleton (`scanner.py`, `alerter.py`, `cron.py`) — imports work
- ✅ `scan_all()` returns a stub for each of the 6 providers
- ✅ `send_discord_alert()` returns False when no webhook is set (no exception)

## Added since the MVP

- ✅ `deploy.sh` — automatic VPS install script (Python venv + cron + logrotate)
- ✅ `docs/operations.md § 11` — VPS install instructions + Discord webhook setup
- ✅ `docs/operations.md § 12` — manifest release flow (signing + S3 upload)

## Planned

- Real HTML scrape parser per provider (BeautifulSoup or lxml)
- Diff against the previous snapshot (cached JSON file)
- Email alert (SMTP) option
- Multiple alert channels for critical price changes
- "Model deprecated" warning in the panel for ABS customers

## Manifest signing flow (vendor side)

Steps to publish a new release (details in `docs/operations.md § 12`):

```bash
# 1) Prepare the manifest
vim manifest.json

# 2) Sign it (fetch private.pem from the secret store)
openssl dgst -sha256 -sign manifest-keys/private.pem -out manifest.json.sig.bin manifest.json
base64 manifest.json.sig.bin > manifest.json.sig

# 3) Upload to S3
aws s3 cp manifest.json     s3://abs-releases/manifest.json
aws s3 cp manifest.json.sig s3://abs-releases/manifest.json.sig
```

On the customer side, verification is fail-closed against `app/update/manifest_pubkey.pem`.
