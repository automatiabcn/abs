#!/usr/bin/env bash
# 025 — One-shot Hetzner / Linux VPS deploy.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/automatiabcn/abs/main/infra/scripts/deploy_hetzner.sh | \
#       bash -s -- --domain abs.example.com --email admin@example.com
#
# Or local:
#   bash infra/scripts/deploy_hetzner.sh --domain abs.example.com --email admin@example.com
#
# Idempotent: re-running upgrades the existing install.

set -euo pipefail

DOMAIN=""
ADMIN_EMAIL=""
SKIP_TLS=0
REPO_URL="https://github.com/automatiabcn/abs.git"
INSTALL_DIR="/opt/abs"
BRANCH="main"

usage() {
  cat <<EOF
Usage: $0 --domain <DOMAIN> --email <ADMIN_EMAIL> [--skip-tls] [--branch <BRANCH>]

Required:
  --domain      DNS name pointing to this server (e.g. abs.example.com)
  --email       Admin email for Let's Encrypt + setup wizard

Optional:
  --skip-tls    Skip Let's Encrypt (use self-signed; for dev/lab)
  --branch      Git branch (default: main)
  --help        Show this message

Examples:
  $0 --domain abs.firmaadi.com --email admin@firmaadi.com
EOF
}

# ---- Argument parsing -------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) ADMIN_EMAIL="$2"; shift 2 ;;
    --skip-tls) SKIP_TLS=1; shift ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$DOMAIN" || -z "$ADMIN_EMAIL" ]]; then
  echo "ERROR: --domain and --email are required." >&2
  usage
  exit 1
fi

# ---- Helpers ----------------------------------------------------------------
log() { echo "[abs-deploy] $*"; }
need_sudo() { [[ $EUID -ne 0 ]] && echo "sudo " || echo ""; }
SUDO="$(need_sudo)"

# ---- Step 1: Docker install -------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "installing docker..."
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker
else
  log "docker already installed: $(docker --version)"
fi

# ---- Step 2: Compose plugin (Docker 20.10+ ships v2 by default) -------------
if ! docker compose version >/dev/null 2>&1; then
  log "installing docker-compose-plugin..."
  $SUDO apt-get update -y || true
  $SUDO apt-get install -y docker-compose-plugin || true
fi

# ---- Step 3: Clone or pull repo --------------------------------------------
if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "updating $INSTALL_DIR"
  $SUDO git -C "$INSTALL_DIR" fetch --all
  $SUDO git -C "$INSTALL_DIR" checkout "$BRANCH"
  $SUDO git -C "$INSTALL_DIR" pull --ff-only
else
  log "cloning $REPO_URL into $INSTALL_DIR"
  $SUDO mkdir -p "$INSTALL_DIR"
  $SUDO git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

# ---- Step 4: .env bootstrap (idempotent) -----------------------------------
ENV_FILE="$INSTALL_DIR/infra/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  log "bootstrapping $ENV_FILE"
  $SUDO tee "$ENV_FILE" >/dev/null <<EOF
ABS_DOMAIN=$DOMAIN
ABS_ADMIN_EMAIL=$ADMIN_EMAIL
ABS_SSL_MODE=$([ "$SKIP_TLS" = "1" ] && echo "internal" || echo "acme")
EOF
else
  log ".env already exists at $ENV_FILE — leaving as-is"
fi

# ---- Step 5: Caddyfile (auto TLS via email) --------------------------------
CADDYFILE="$INSTALL_DIR/infra/Caddyfile"
if [[ ! -f "$CADDYFILE" ]]; then
  log "writing Caddyfile (TLS skip=$SKIP_TLS)"
  if [[ "$SKIP_TLS" = "1" ]]; then
    $SUDO tee "$CADDYFILE" >/dev/null <<EOF
:80, :443 {
  tls internal
  reverse_proxy backend:8000
}
EOF
  else
    $SUDO tee "$CADDYFILE" >/dev/null <<EOF
$DOMAIN {
  tls $ADMIN_EMAIL
  reverse_proxy backend:8000
}
EOF
  fi
else
  log "Caddyfile present"
fi

# ---- Step 6: Vault key bootstrap (idempotent) -------------------------------
VAULT_DIR="$INSTALL_DIR/infra/vault-key"
if [[ ! -f "$VAULT_DIR/age.txt" ]]; then
  log "generating age master key (one-time)"
  $SUDO mkdir -p "$VAULT_DIR"
  if command -v age-keygen >/dev/null 2>&1; then
    $SUDO age-keygen -o "$VAULT_DIR/age.txt"
  else
    log "WARNING: age-keygen not found — vault will run in console-fallback mode."
    log "         Install: $SUDO apt-get install age (or brew install age on macOS)"
  fi
fi

# ---- Step 7: Compose up -----------------------------------------------------
log "bringing services up"
$SUDO docker compose -f "$INSTALL_DIR/infra/docker-compose.yml" pull || true
$SUDO docker compose -f "$INSTALL_DIR/infra/docker-compose.yml" up -d --build

# ---- Step 8: Wait for health ------------------------------------------------
log "waiting for /healthz..."
HEALTHY=0
for i in $(seq 1 60); do
  if curl -fsSk "https://$DOMAIN/healthz" >/dev/null 2>&1 \
     || curl -fsS "http://$DOMAIN/healthz" >/dev/null 2>&1; then
    HEALTHY=1; break
  fi
  sleep 2
done

if [[ "$HEALTHY" = "1" ]]; then
  log "✅ deploy complete!"
  log "   panel: https://$DOMAIN/setup"
  log "   docs:  https://$DOMAIN/docs"
  log "   API:   https://$DOMAIN/v1/health/full"
else
  log "⚠️  /healthz not reachable after 120s — check 'docker compose logs backend'"
  exit 1
fi
