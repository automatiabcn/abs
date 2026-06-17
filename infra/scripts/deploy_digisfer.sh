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
# (preserving the box-local Caddyfile + untracked .env) → reclaim disk + gate on
# free space → rebuild the locally built images → gate on /healthz. No migration
# step — the SQLite schema self-heals on boot (create_all + the column reconciler).
#
# Why the disk step: every `--build` leaves the previous backend image dangling,
# and the ollama (~3.4G) + whisperx (~2.5G) images need ~6G to (re)pull. Without
# a guard the box silently fills `/var/lib/docker` and the build dies mid-extract
# with a cryptic "no space left on device". We prune dangling images + build
# cache (targeted only — never `system`/`volume` prune, which has broken
# neighbouring stacks on shared hosts) and fail fast with guidance if still low.
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
# Disk gate: minimum free GiB required before a rebuild (the ollama + whisperx
# images alone need ~6G on a first/changed pull). Override on a roomy box, or
# set ABS_SKIP_DISK_GATE=1 to bypass the abort entirely.
MIN_FREE_GB="${ABS_MIN_FREE_GB:-6}"
SKIP_DISK_GATE="${ABS_SKIP_DISK_GATE:-0}"

log() { echo "[deploy-digisfer] $*"; }

# Reclaim safely-removable space, then refuse to rebuild if the box is still too
# full to (re)pull the stack — turning a cryptic mid-extract crash into an
# actionable, early failure. Targeted prune ONLY: dangling images + build cache.
# We never prune volumes, named images in use, or running containers.
reclaim_and_check_disk() {
  local root avail_kb avail_gb
  root="$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
  log "3/5 reclaim disk before build (docker root: $root)"
  docker image prune -f   >/dev/null 2>&1 || true   # untagged (old --build) layers
  docker builder prune -f >/dev/null 2>&1 || true   # stale build cache
  docker system df 2>/dev/null || true
  # Measure the docker root's filesystem; fall back to "/" if that path can't be
  # stat'd (e.g. an unusual root dir), so the gate still protects the box.
  avail_kb="$(df -Pk "$root" 2>/dev/null | awk 'NR==2 {print $4}')"
  [ -n "${avail_kb:-}" ] || avail_kb="$(df -Pk / 2>/dev/null | awk 'NR==2 {print $4}')"
  if [ -z "${avail_kb:-}" ]; then
    log "WARN — could not measure free space on $root; skipping disk gate"
    return 0
  fi
  avail_gb=$(( avail_kb / 1024 / 1024 ))
  log "free space on $root: ${avail_gb} GiB (need >= ${MIN_FREE_GB} GiB)"
  if [ "$SKIP_DISK_GATE" != "1" ] && [ "$avail_gb" -lt "$MIN_FREE_GB" ]; then
    log "ERROR — not enough free disk to rebuild the stack safely."
    log "  ollama (~3.4G) + whisperx (~2.5G) need ~6G on a first/changed pull."
    log "  On the box, free space then re-run, e.g.:"
    log "    * docker image prune -af        # drop ALL unused images (not just dangling)"
    log "    * grow the EBS volume / filesystem"
    log "  ...or set ABS_SKIP_DISK_GATE=1 to override this guard."
    exit 1
  fi
}

# Use sudo only when the agent user can't write the install dir itself. The
# recommended setup chowns /opt/abs to the Jenkins user → SUDO stays empty (no
# broad sudo needed); a root-owned dir falls back to passwordless `sudo git`.
SUDO=""
[ -w "$INSTALL_DIR" ] || SUDO="sudo"

cd "$INSTALL_DIR"

log "1/5 backup SQLite (abs.db)"
$SUDO mkdir -p "$INSTALL_DIR/backups"
docker run --rm -v "${DATA_VOLUME}:/d" -v "$INSTALL_DIR/backups:/b" alpine \
  sh -c 'cp -f /d/abs.db /b/abs.$(date +%s).db' || log "backup skipped (db not present yet)"
# retain the 10 most recent backups
$SUDO sh -c "ls -1t '$INSTALL_DIR'/backups/abs.*.db 2>/dev/null | tail -n +11 | xargs -r rm -f" || true

log "2/5 update $INSTALL_DIR to origin/$BRANCH (preserve local Caddyfile + .env)"
$SUDO git stash push -- infra/Caddyfile 2>/dev/null || true   # box-local domain edit
$SUDO git fetch origin "$BRANCH"
$SUDO git reset --hard "origin/$BRANCH"
$SUDO git stash pop 2>/dev/null || true                       # .env is untracked → untouched
DEPLOYED="$($SUDO git rev-parse --short HEAD)"

reclaim_and_check_disk

log "4/5 rebuild + restart stack ($DEPLOYED)"
docker compose -f "$COMPOSE" up -d --build --remove-orphans

log "5/5 health gate ($HEALTH_URL)"
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
