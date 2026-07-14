#!/usr/bin/env bash
# Build the single-file customer tarball.
#
# Usage:
#   ./scripts/build_customer_pkg.sh <slug>
#
# `<slug>` is the directory name under customer-keys/ produced by
# scripts/customer_onboard.sh (e.g. `acmecorp-1234567890`).
#
# Output:
#   customer-keys/<slug>/customer-pkg-<slug>.tar.gz
#
# Contents (every host bind mount the customer compose references PLUS
# the credential files the customer needs at first boot):
#   docker-compose.yml        — ./
#   Caddyfile                 — ./Caddyfile -> /etc/caddy/Caddyfile:ro
#   cerbos/                   — ./cerbos -> /etc/cerbos:ro
#   scripts/                  — ./scripts -> /app/infra/scripts:ro
#   license.jwt               — paste into ABS_LICENSE_KEY .env var
#   ghcr_pull.token           — `docker login ghcr.io --password-stdin`
#   founder_actions.md        — pre-send checklist (founder copy only,
#                               keep for audit; safe to leave in tarball
#                               because it carries no secrets — just PAT
#                               generation instructions)
#
# The tarball is the single artefact you ship over an encrypted channel;
# the customer extracts it into /opt/abs/ and runs `docker compose up -d`.
# This pattern replaces the pre-Sprint-2N "attach 4 separate files +
# manually instruct cerbos/ recreation" flow that broke an early install (the
# bug log #2M-D).

set -euo pipefail

SLUG="${1:?usage: build_customer_pkg.sh <customer-slug>}"
KEYS_DIR="customer-keys/${SLUG}"

if [ ! -d "${KEYS_DIR}" ]; then
  echo "ERROR: ${KEYS_DIR} not found. Run scripts/customer_onboard.sh first." >&2
  exit 1
fi

# Verify every host bind mount target is present before tar — fail fast
# rather than ship an incomplete bundle.
REQUIRED=(
  "docker-compose.yml"
  "Caddyfile"
  "cerbos"
  "scripts"
  "license.jwt"
  "ghcr_pull.token"
)
missing=()
for item in "${REQUIRED[@]}"; do
  if [ ! -e "${KEYS_DIR}/${item}" ]; then
    missing+=("${item}")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: ${KEYS_DIR} missing required files: ${missing[*]}" >&2
  echo "       Re-run scripts/customer_onboard.sh to repopulate." >&2
  exit 1
fi

PKG_NAME="customer-pkg-${SLUG}.tar.gz"
PKG_FILE="${KEYS_DIR}/${PKG_NAME}"

# Excluded from the tarball: the tarball itself (if re-run), email.md
# (founder copy of the welcome email; not customer-side material).
tar -czf "${PKG_FILE}" \
  --exclude="${PKG_NAME}" \
  --exclude="email.md" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude=".DS_Store" \
  -C "${KEYS_DIR}" \
  docker-compose.yml \
  Caddyfile \
  cerbos \
  scripts \
  license.jwt \
  ghcr_pull.token \
  founder_actions.md

SIZE=$(wc -c < "${PKG_FILE}" | tr -d ' ')
echo "Package: ${PKG_FILE} (${SIZE} bytes)"
echo ""
echo "Customer-side recipe (paste into the welcome email if not already there):"
echo "  cd /opt/abs && tar -xzvf ${PKG_NAME}"
echo "  ls /opt/abs   # docker-compose.yml + Caddyfile + cerbos/ + scripts/ + ..."
echo ""
echo "Tarball contents:"
tar -tzf "${PKG_FILE}" | sed 's/^/  /'
