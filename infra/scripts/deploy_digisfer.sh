#!/usr/bin/env bash
# On-box deploy for the digisfer customer (AWS EC2 · docker-compose · SQLite).
#
# Orchestrator-agnostic: run it FROM the box (Jenkins agent, GitHub self-hosted
# runner, AWS SSM, or by hand). Because it runs on the box there is NO inbound
# SSH — port 22 can stay closed; the agent reaches the repo over outbound 443.
#
#   bash infra/scripts/deploy_digisfer.sh
#
# Idempotent. Steps: back up abs.db → fast-forward /opt/abs to origin/main
# (preserving the box-local Caddyfile + untracked .env) → rebuild the locally
# built images → gate on /healthz. No migration step — the SQLite schema
# self-heals on boot (create_all + the column reconciler).
#
# Requirements on the box:
#   - the runner user has passwordless `sudo git` (or owns $INSTALL_DIR), and is
#     in the `docker` group;
#   - origin already points at github.com/automatiabcn/abs.
set -euo pipefail

INSTALL_DIR="${ABS_INSTALL_DIR:-/opt/abs}"
BRANCH="${ABS_DEPLOY_BRANCH:-main}"
COMPOSE="$INSTALL_DIR/infra/docker-compose.yml"
DATA_VOLUME="${ABS_DATA_VOLUME:-infra_abs-data}"
HEALTH_URL="${ABS_HEALTH_URL:-http://localhost/healthz}"

log() { echo "[deploy-digisfer] $*"; }

cd "$INSTALL_DIR"

log "1/4 backup SQLite (abs.db)"
sudo mkdir -p "$INSTALL_DIR/backups"
docker run --rm -v "${DATA_VOLUME}:/d" -v "$INSTALL_DIR/backups:/b" alpine \
  sh -c 'cp -f /d/abs.db /b/abs.$(date +%s).db' || log "backup skipped (db not present yet)"
# retain the 10 most recent backups
sudo sh -c "ls -1t '$INSTALL_DIR'/backups/abs.*.db 2>/dev/null | tail -n +11 | xargs -r rm -f" || true

log "2/4 update $INSTALL_DIR to origin/$BRANCH (preserve local Caddyfile + .env)"
sudo git stash push -- infra/Caddyfile 2>/dev/null || true   # box-local domain edit
sudo git fetch origin "$BRANCH"
sudo git reset --hard "origin/$BRANCH"
sudo git stash pop 2>/dev/null || true                       # .env is untracked → untouched
DEPLOYED="$(sudo git rev-parse --short HEAD)"

log "3/4 rebuild + restart stack ($DEPLOYED)"
docker compose -f "$COMPOSE" up -d --build --remove-orphans

log "4/4 health gate ($HEALTH_URL)"
for _ in $(seq 1 36); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    log "deploy OK — $DEPLOYED healthy"
    exit 0
  fi
  sleep 5
done
log "ERROR — /healthz not reachable after ~3m; recent backend logs:"
docker compose -f "$COMPOSE" logs --tail=60 backend || true
exit 1
