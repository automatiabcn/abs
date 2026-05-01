#!/usr/bin/env bash
# 027 Modul E — Vault master-key escrow bootstrap.
#
# Usage:
#   bash infra/scripts/vault_escrow_setup.sh --target onepassword
#   bash infra/scripts/vault_escrow_setup.sh --target s3 --bucket abs-vault-escrow
#   bash infra/scripts/vault_escrow_setup.sh --target zip --password-env ABS_ESCROW_PASS
#   bash infra/scripts/vault_escrow_setup.sh --dry-run --target onepassword
#
# Idempotent: if today's escrow already exists, the script logs and exits 0.

set -euo pipefail

KEY_PATH="${ABS_VAULT_KEY_PATH:-/opt/abs/infra/vault-key/age.txt}"
TARGET=""
BUCKET=""
PASSWORD_ENV=""
DRY_RUN=0
ITEM_TITLE_PREFIX="abs-vault-master-key"

usage() {
  cat <<EOF
Usage: $0 --target {onepassword|s3|zip} [options]

Required:
  --target onepassword    Escrow via 1Password CLI (op)
  --target s3             Escrow via AWS S3 SSE-KMS
  --target zip            Local encrypted ZIP (7z)

Options:
  --bucket <name>         S3 bucket (required for --target s3)
  --password-env <var>    Env var holding ZIP password (required for --target zip)
  --key <path>            Override master key path (default: $KEY_PATH)
  --dry-run               Print what would happen, do not write
  --help

Examples:
  $0 --target onepassword
  $0 --target s3 --bucket abs-vault-escrow-eu
  $0 --target zip --password-env ABS_ESCROW_PASS
EOF
}

log() { echo "[escrow] $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --bucket) BUCKET="$2"; shift 2 ;;
    --password-env) PASSWORD_ENV="$2"; shift 2 ;;
    --key) KEY_PATH="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: --target is required" >&2
  usage
  exit 1
fi

if [[ ! -f "$KEY_PATH" ]] && [[ "$DRY_RUN" = "0" ]]; then
  echo "ERROR: master key not found at $KEY_PATH" >&2
  exit 2
fi

DATESTAMP="$(date -u +%Y-%m-%d)"
ITEM_TITLE="${ITEM_TITLE_PREFIX}-${DATESTAMP}"

case "$TARGET" in
  onepassword)
    if [[ "$DRY_RUN" = "1" ]]; then
      log "DRY-RUN: would create 1Password document '$ITEM_TITLE' in 'ABS Production' vault"
      exit 0
    fi
    if ! command -v op >/dev/null 2>&1; then
      echo "ERROR: 1Password CLI 'op' not found. Install: https://1password.com/downloads/command-line/" >&2
      exit 3
    fi
    # Check if today's item already exists (idempotent)
    if op item get "$ITEM_TITLE" --vault "ABS Production" >/dev/null 2>&1; then
      log "1Password item '$ITEM_TITLE' already exists — skipping"
      exit 0
    fi
    op document create "$KEY_PATH" --title "$ITEM_TITLE" --vault "ABS Production"
    log "Escrow created: 1Password / ABS Production / $ITEM_TITLE"
    ;;

  s3)
    if [[ -z "$BUCKET" ]]; then
      echo "ERROR: --bucket required for --target s3" >&2
      exit 1
    fi
    if [[ "$DRY_RUN" = "1" ]]; then
      log "DRY-RUN: would upload to s3://${BUCKET}/${ITEM_TITLE}.txt with sse:aws:kms"
      exit 0
    fi
    if ! command -v aws >/dev/null 2>&1; then
      echo "ERROR: aws CLI not found." >&2
      exit 3
    fi
    aws s3 cp "$KEY_PATH" "s3://${BUCKET}/${ITEM_TITLE}.txt" \
        --sse aws:kms \
        --metadata "abs-escrow=true,date=${DATESTAMP}"
    log "Escrow created: s3://${BUCKET}/${ITEM_TITLE}.txt"
    ;;

  zip)
    if [[ -z "$PASSWORD_ENV" ]]; then
      echo "ERROR: --password-env required for --target zip" >&2
      exit 1
    fi
    if [[ "$DRY_RUN" = "1" ]]; then
      log "DRY-RUN: would create encrypted ZIP escrow-${DATESTAMP}.7z (password from \$$PASSWORD_ENV)"
      exit 0
    fi
    if ! command -v 7z >/dev/null 2>&1; then
      echo "ERROR: 7z not found. Install: brew install p7zip / apt-get install p7zip-full" >&2
      exit 3
    fi
    pass="${!PASSWORD_ENV:-}"
    if [[ -z "$pass" ]]; then
      echo "ERROR: env var \$$PASSWORD_ENV is empty" >&2
      exit 4
    fi
    out_file="escrow-${DATESTAMP}.7z"
    if [[ -f "$out_file" ]]; then
      log "ZIP escrow '$out_file' already exists — skipping"
      exit 0
    fi
    7z a -p"${pass}" "$out_file" "$KEY_PATH" >/dev/null
    log "Escrow created: $out_file (move to offline storage immediately)"
    ;;

  *)
    echo "ERROR: unknown target: $TARGET (use onepassword|s3|zip)" >&2
    exit 1
    ;;
esac

log "Escrow OK — verify by reading back: $TARGET / $ITEM_TITLE"
