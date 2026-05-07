#!/usr/bin/env bash
# Customer onboarding — single-command per-customer setup.
# Generates SSH deploy key (read-only), registers on GitHub, mints
# license JWT, and produces an email template for the customer.
#
# Usage:
#   ./scripts/customer_onboard.sh "Acme Corp" "admin@acme.com" team 5 365 [machine_fp_hex]
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

set -euo pipefail

CUSTOMER_NAME="${1:?customer name required}"
CUSTOMER_EMAIL="${2:?customer email required}"
TIER="${3:-self-host}"
SEATS="${4:-1}"
VALID_DAYS="${5:-365}"
MACHINE_FP="${6:-}"

CUSTOMER_SLUG=$(echo "$CUSTOMER_NAME" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')
KEYS_DIR="customer-keys/${CUSTOMER_SLUG}"

if [ -d "$KEYS_DIR" ]; then
  echo "WARN: ${KEYS_DIR} already exists — refusing to overwrite."
  echo "      Delete the directory first if you want to re-onboard."
  exit 1
fi

mkdir -p "$KEYS_DIR"
chmod 700 "$KEYS_DIR"

echo "[1/4] Generating SSH deploy key…"
ssh-keygen -t ed25519 -C "abs-deploy-${CUSTOMER_SLUG}" \
  -f "${KEYS_DIR}/deploy_key" -N "" -q
chmod 600 "${KEYS_DIR}/deploy_key"

echo "[2/4] Registering deploy key on GitHub (read-only)…"
gh repo deploy-key add "${KEYS_DIR}/deploy_key.pub" \
  --repo=enzoemir1/abs \
  --title="${CUSTOMER_NAME}" \
  -- 2>&1 | tee "${KEYS_DIR}/github_register.log" || {
  echo "WARN: deploy-key registration failed — see ${KEYS_DIR}/github_register.log"
}

echo "[3/4] Minting license JWT…"
if [ -n "${MACHINE_FP}" ]; then
  MFP_ARG="machine_fp='${MACHINE_FP}'"
  echo "      machine_fp binding: ${MACHINE_FP:0:12}…"
else
  MFP_ARG="machine_fp=None"
  echo "      no machine_fp — legacy mode (license portable across hosts)"
fi
LICENSE_TOKEN=$(docker compose -f infra/docker-compose.yml exec -T backend \
  python -c "
from app.licensing import generate_license
print(generate_license('${CUSTOMER_EMAIL}', tier='${TIER}', seat_count=${SEATS}, valid_days=${VALID_DAYS}, ${MFP_ARG}))
" 2>/dev/null | tail -1)

if [ -z "$LICENSE_TOKEN" ]; then
  echo "ERROR: license mint failed — backend container running?"
  exit 1
fi

echo "$LICENSE_TOKEN" > "${KEYS_DIR}/license.jwt"
chmod 600 "${KEYS_DIR}/license.jwt"

echo "[4/4] Generating onboarding email…"
cat > "${KEYS_DIR}/email.md" <<EOF
Subject: Automatia ABS — Welcome ${CUSTOMER_NAME}

Hi,

Your Automatia ABS license is ready. Setup steps:

1. Place the attached deploy_key on your server (chmod 600).

2. Clone the repo:
   GIT_SSH_COMMAND="ssh -i deploy_key -o StrictHostKeyChecking=no" \\
     git clone git@github.com:enzoemir1/abs.git
   cd abs

3. Bring up Docker Compose:
   docker compose -f infra/docker-compose.yml up -d

4. Visit https://YOUR-DOMAIN.com/setup
   - Set admin email + password
   - Step 2: paste this license token:

${LICENSE_TOKEN}

   - Configure provider keys (Groq, Anthropic, etc.) — bring your own.

5. Read docs/customer-agreement.md and reply "I accept" to confirm.

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
echo "Send to customer (${CUSTOMER_EMAIL}):"
echo "  - deploy_key (private SSH key — encrypted channel only!)"
echo "  - email.md (instructions + license token)"
echo "  - docs/customer-agreement.md (require signed acceptance)"
echo ""
echo "Revoke later:"
echo "  gh repo deploy-key list --repo=enzoemir1/abs"
echo "  gh repo deploy-key delete <id>"
