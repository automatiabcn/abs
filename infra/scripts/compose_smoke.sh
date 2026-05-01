#!/usr/bin/env bash
# 024 — Docker compose production smoke check.
#
# Brings up infra/docker-compose.yml services, waits for /healthz, captures
# state, and tears down. Output JSON: /tmp/abs-024-smoke/evidence/06_compose_health.json
#
# Usage:
#   bash infra/scripts/compose_smoke.sh         # full up + down
#   SKIP_BUILD=1 bash infra/scripts/compose_smoke.sh
#
# Exit 0 on success (services up + /healthz 200); 1 otherwise.

set -e

EVIDENCE_DIR="/tmp/abs-024-smoke/evidence"
mkdir -p "$EVIDENCE_DIR"

OUT="$EVIDENCE_DIR/06_compose_health.json"
LOG="/tmp/abs-024-smoke/compose.log"

cd "$(dirname "$0")/.." || exit 1
cd ..  # repo root

# Default port mapping for backend health probe
HOST_PORT="${ABS_BACKEND_HOST_PORT:-8088}"
TIMEOUT="${ABS_COMPOSE_TIMEOUT:-90}"

started_at=$(date +%s)

echo "{\"step\": \"compose_up_started\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$OUT"

# Bring up services (cached build)
if [ "${SKIP_BUILD:-0}" = "0" ]; then
  echo "[smoke] docker compose -f infra/docker-compose.yml up -d"
  if ! docker compose -f infra/docker-compose.yml up -d --build > "$LOG" 2>&1; then
    echo "[smoke] docker compose up FAILED — see $LOG"
    cat <<EOF > "$OUT"
{
  "ok": false,
  "step": "docker_compose_up_failed",
  "log_path": "$LOG",
  "error": "compose up exited non-zero",
  "elapsed_s": $(( $(date +%s) - started_at ))
}
EOF
    exit 1
  fi
fi

# Wait for healthz
HEALTHY=0
for i in $(seq 1 "$TIMEOUT"); do
  if curl -fsS -m 2 "http://localhost:$HOST_PORT/healthz" > /tmp/abs-024-healthz.json 2>/dev/null; then
    HEALTHY=1
    break
  fi
  sleep 1
done

elapsed=$(( $(date +%s) - started_at ))

if [ "$HEALTHY" = "1" ]; then
  HEALTHZ_BODY=$(cat /tmp/abs-024-healthz.json)
  cat <<EOF > "$OUT"
{
  "ok": true,
  "host_port": $HOST_PORT,
  "elapsed_s": $elapsed,
  "healthz_response": $HEALTHZ_BODY
}
EOF
  echo "[smoke] healthy after ${elapsed}s"
  RC=0
else
  cat <<EOF > "$OUT"
{
  "ok": false,
  "step": "healthz_timeout",
  "host_port": $HOST_PORT,
  "elapsed_s": $elapsed,
  "timeout_s": $TIMEOUT,
  "error": "healthz did not respond 200 within timeout"
}
EOF
  echo "[smoke] healthz timeout after ${TIMEOUT}s"
  RC=1
fi

# Always tear down
docker compose -f infra/docker-compose.yml down --remove-orphans >> "$LOG" 2>&1 || true

exit $RC
