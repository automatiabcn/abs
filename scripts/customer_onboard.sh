#!/usr/bin/env bash
# Customer onboarding — single-command per-customer setup.
# Q12 IP-Hardening R3: customer never sees source. Onboarding produces a
# manual ghcr.io PAT instruction (founder generates it via web UI),
# mints the license JWT, and writes an image-pull email template.
#
# Usage:
#   ./scripts/customer_onboard.sh "Acme Corp" "admin@acme.com" team 5 365 [machine_fp_hex] [github_user]
#
# Args:
#   $1 customer name (free text)
#   $2 customer email
#   $3 tier (self-host | team | enterprise | beta) — default: self-host
#   $4 seats — default: 1
#   $5 valid days — default: 365
#   $6 machine_fp (Q12 R1) — optional SHA-256 hex of customer's host
#      fingerprint (run `python -m app.licensing.fingerprint --print`
#      on their server). When set, license is bound to that machine.
#   $7 customer GitHub username — used in the email's `docker login`
#      example. Defaults to the literal "<your-github-user>" placeholder
#      when omitted, prompting the customer to substitute it.

set -euo pipefail

CUSTOMER_NAME="${1:?customer name required}"
CUSTOMER_EMAIL="${2:?customer email required}"
TIER="${3:-self-host}"
SEATS="${4:-1}"
VALID_DAYS="${5:-365}"
MACHINE_FP="${6:-}"
CUSTOMER_GITHUB_USER="${7:-<your-github-user>}"

CUSTOMER_SLUG=$(echo "$CUSTOMER_NAME" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')
KEYS_DIR="customer-keys/${CUSTOMER_SLUG}"
PAT_NAME="abs-pull-${CUSTOMER_SLUG}-$(date +%Y%m)"

if [ -d "$KEYS_DIR" ]; then
  echo "WARN: ${KEYS_DIR} already exists — refusing to overwrite."
  echo "      Delete the directory first if you want to re-onboard."
  exit 1
fi

mkdir -p "$KEYS_DIR"
chmod 700 "$KEYS_DIR"

echo "[1/5] Recording founder action items (PAT generation)…"
cat > "${KEYS_DIR}/founder_actions.md" <<EOF
# Founder action items — ${CUSTOMER_NAME}

The customer never sees source code. Issue them a ghcr.io read-only PAT
so they can \`docker compose pull\` the pre-built images.

1. Open https://github.com/settings/tokens?type=beta and click
   "Generate new token (Beta)".
2. Configure:
   - Token name: ${PAT_NAME}
   - Expiration: 30 days (renew at next invoice cycle)
   - Resource owner: enzoemir1
   - Repository access: "Public repositories (read-only)" is sufficient
   - Permissions → Account → "Packages": **Read-only**
3. Copy the token value (starts with \`github_pat_\`) into
   ${KEYS_DIR}/ghcr_pull.token, then \`chmod 600\` that file.
4. Hand the token + email + license.jwt to the customer over an
   encrypted channel (1Password / Bitwarden share / signed email).
EOF
chmod 600 "${KEYS_DIR}/founder_actions.md"

echo "[2/5] Placeholder for ghcr.io read-only PAT…"
# Founder fills this in after step 1 above. The placeholder makes the
# missing step obvious during a dry-run smoke test.
cat > "${KEYS_DIR}/ghcr_pull.token" <<EOF
__REPLACE_WITH_PAT_FROM_GITHUB__
EOF
chmod 600 "${KEYS_DIR}/ghcr_pull.token"

echo "[3/5] Minting license JWT (host Python, no backend container)…"
if [ -n "${MACHINE_FP}" ]; then
  echo "      machine_fp binding: ${MACHINE_FP:0:12}…"
else
  echo "      no machine_fp — legacy mode (license portable across hosts)"
fi

# Resolve RSA private key path. Order:
#   1. $ABS_PRIVATE_KEY_PATH (explicit override)
#   2. $HOME/.config/automatia/abs-manifest-signing-private.pem (founder local)
#   3. ssh ai-pc:~/keys/abs-manifest-signing-private.pem (fetch to temp 0600 file)
KEY_PATH=""
TMP_KEY=""
cleanup_tmp_key() {
  if [ -n "${TMP_KEY}" ] && [ -f "${TMP_KEY}" ]; then
    rm -f "${TMP_KEY}"
  fi
}
trap cleanup_tmp_key EXIT

if [ -n "${ABS_PRIVATE_KEY_PATH:-}" ] && [ -f "${ABS_PRIVATE_KEY_PATH}" ]; then
  KEY_PATH="${ABS_PRIVATE_KEY_PATH}"
  echo "      key source: \$ABS_PRIVATE_KEY_PATH"
elif [ -f "${HOME}/.config/automatia/abs-manifest-signing-private.pem" ]; then
  KEY_PATH="${HOME}/.config/automatia/abs-manifest-signing-private.pem"
  echo "      key source: ${HOME}/.config/automatia/"
elif ssh -o ConnectTimeout=3 -o BatchMode=yes ai-pc \
       'test -f ~/keys/abs-manifest-signing-private.pem' 2>/dev/null; then
  TMP_KEY="$(mktemp -t abs-mint-key.XXXXXX)"
  chmod 600 "${TMP_KEY}"
  ssh -o BatchMode=yes ai-pc 'cat ~/keys/abs-manifest-signing-private.pem' \
    > "${TMP_KEY}"
  if [ ! -s "${TMP_KEY}" ]; then
    echo "ERROR: ssh fetch returned empty key"; exit 1
  fi
  KEY_PATH="${TMP_KEY}"
  echo "      key source: ssh ai-pc (fetched to ${TMP_KEY})"
else
  echo "ERROR: RSA private key not found. Set ABS_PRIVATE_KEY_PATH, place"
  echo "       the PEM at ~/.config/automatia/, or ensure ssh ai-pc works."
  exit 1
fi

# Pre-flight: pyjwt + cryptography on host Python.
if ! python3 -c "import jwt, cryptography" 2>/dev/null; then
  echo "ERROR: host python3 missing pyjwt or cryptography."
  echo "       Install with: pip3 install pyjwt cryptography"
  exit 1
fi

LICENSE_TOKEN=$(
  ABS_PRIVATE_KEY_PATH="${KEY_PATH}" \
  MINT_EMAIL="${CUSTOMER_EMAIL}" \
  MINT_TIER="${TIER}" \
  MINT_SEATS="${SEATS}" \
  MINT_VALID_DAYS="${VALID_DAYS}" \
  MINT_MACHINE_FP="${MACHINE_FP}" \
  python3 scripts/_mint_license.py 2>&1 | tail -1
)

if [ -z "$LICENSE_TOKEN" ] || [[ "$LICENSE_TOKEN" == *"Traceback"* ]] \
   || [[ "$LICENSE_TOKEN" != *.*.* ]]; then
  echo "ERROR: license mint failed — output: ${LICENSE_TOKEN}"
  exit 1
fi

echo "$LICENSE_TOKEN" > "${KEYS_DIR}/license.jwt"
chmod 600 "${KEYS_DIR}/license.jwt"

echo "[4/5] Copying customer compose + Caddyfile + Cerbos policies + cron scripts…"
cp infra/docker-compose.customer.yml "${KEYS_DIR}/docker-compose.yml"
if [ -f infra/Caddyfile ]; then
  cp infra/Caddyfile "${KEYS_DIR}/Caddyfile"
fi
# BUG-27 — the cerbos service in the compose mounts ./cerbos read-only at
# /cerbos. Bundle the engine config + policies so the customer's
# `docker compose up -d` finds them in the same directory as the compose.
if [ -d infra/cerbos ]; then
  rm -rf "${KEYS_DIR}/cerbos"
  cp -R infra/cerbos "${KEYS_DIR}/cerbos"
fi
# Sprint 2N FAZ D (smebes lesson 18) — email-cron service mounts
# ./scripts:/app/infra/scripts:ro at runtime. Without the host scripts
# directory the cron container exits immediately ("No such file or
# directory: infra/scripts/email_tick.py"). Bundle the cron scripts
# alongside docker-compose.yml so every customer's `docker compose up -d`
# finds the same files the compose file is wired against.
if [ -d infra/scripts ]; then
  rm -rf "${KEYS_DIR}/scripts"
  cp -R infra/scripts "${KEYS_DIR}/scripts"
fi

echo "[5/5] Generating onboarding email…"
cat > "${KEYS_DIR}/email.md" <<EOF
Subject: Automatia ABS — Welcome ${CUSTOMER_NAME}

Hi,

Your Automatia ABS license is ready. Setup uses pre-built Docker images;
you do not need any source code.

1. Provision a Linux VPS (Hetzner CX22 / DigitalOcean / AWS micro).
   Minimum: 2 GB RAM, 20 GB disk, public IPv4.

2. Install Docker:
   curl -fsSL https://get.docker.com | sh

3. Easiest path — extract the single attached tarball into /opt/abs/:
     cd /opt/abs && tar -xzvf customer-pkg-${CUSTOMER_SLUG}.tar.gz
     ls /opt/abs   # docker-compose.yml + Caddyfile + cerbos/ + scripts/
                   # + license.jwt + ghcr_pull.token

   (Equivalent manual list — extract the tarball or copy each item:)
     docker-compose.yml      # this customer compose
     Caddyfile               # reverse proxy config
     ghcr_pull.token         # read-only token to pull our images
     license.jwt             # your signed license
     cerbos/                 # authorization engine config + policies (REQUIRED)
       config.yaml
       policies/*.yaml
     scripts/                # email-cron + housekeeping scripts (REQUIRED)
       email_tick.py
       ...

   Note: cerbos/ is mounted read-only at /etc/cerbos and scripts/ is
   mounted read-only at /app/infra/scripts. Without either directory
   the related container exits immediately on boot.

   Create /opt/abs/.env with:
     ABS_PUBLIC_URL=https://your-domain.com
     ABS_VERSION=1.0.1
     ABS_VAULT_KEY=\$(openssl rand -base64 32)
     ABS_DB_PASSWORD=\$(openssl rand -base64 32)
     # plus your provider keys (Groq, Anthropic, etc.) — bring your own.

   Note: ABS_DB_PASSWORD is REQUIRED from 1.0.1 onwards. The stack ships
   with Postgres 16 by default so the Sprint 2K Row-Level Security
   policies (KVKK / GDPR defense-in-depth) are active. To stay on the
   single-tenant SQLite path, also add:
     ABS_DATABASE_URL=sqlite:////app/data/abs.db
   and leave ABS_DB_PASSWORD set anyway (Postgres still starts).

4. Authenticate with our private container registry:
   cat ghcr_pull.token | docker login ghcr.io -u ${CUSTOMER_GITHUB_USER} --password-stdin

5. Pull the images and start the stack:
   cd /opt/abs && docker compose pull && docker compose up -d

6. Visit https://your-domain.com/setup
   - Step 1: admin email + password
   - Step 2: paste this license token:

${LICENSE_TOKEN}

   - Steps 3-6: configure your own provider keys (Groq, Anthropic, etc.).

7. Read docs/customer-agreement.md (attached) and reply "I accept".

Tier:    ${TIER}
Seats:   ${SEATS}
Valid:   ${VALID_DAYS} days
Support: support@automatiabcn.com

— Automatia BCN
EOF

echo ""
echo "=== Done ==="
echo "Output files in ${KEYS_DIR}/:"
ls -la "${KEYS_DIR}/"
echo ""
echo "Founder steps (see ${KEYS_DIR}/founder_actions.md):"
echo "  1. Generate fine-grained PAT named ${PAT_NAME}"
echo "  2. Save it into ${KEYS_DIR}/ghcr_pull.token (replacing the placeholder)"
echo ""
echo "Send to customer (${CUSTOMER_EMAIL}):"
echo "  - docker-compose.yml"
echo "  - Caddyfile"
echo "  - ghcr_pull.token (encrypted channel only!)"
echo "  - license.jwt"
echo "  - email.md"
echo "  - docs/customer-agreement.md (require signed acceptance)"
echo ""
echo "Revoke later:"
echo "  Open https://github.com/settings/tokens?type=beta and delete ${PAT_NAME}"
