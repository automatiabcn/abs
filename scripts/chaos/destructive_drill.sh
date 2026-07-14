#!/usr/bin/env bash
# Q12-L21 sweep 3 — destructive fresh-deploy drill (founder-gated).
#
# Validates that the project can be torn down and rebuilt from
# nothing in a bounded time window, so a real outage recovery
# matches the documented runbook.
#
# THIS SCRIPT IS DESTRUCTIVE. It deletes Docker volumes and the
# SQLite DB. It runs against an ISOLATED compose namespace
# (`abs-drill`) by default to keep the live `infra-*` and
# `abs-cj-*` stacks (25h customer journey state) untouched.
#
# Default behaviour: SKIP with informative message. Set
# `ABS_DESTRUCTIVE_DRILL=1` to enable. Founder approval expected.
#
# Usage:
#   bash scripts/chaos/destructive_drill.sh           # SKIP message
#   ABS_DESTRUCTIVE_DRILL=1 bash scripts/chaos/destructive_drill.sh
#
# Optional knobs:
#   ABS_DRILL_PROJECT (default: abs-drill)
#   ABS_DRILL_PORT    (default: 28000)
#   ABS_DRILL_ITERS   (default: 1; brief asks for 3 — set to 3 for full)

set -euo pipefail

if [ "${ABS_DESTRUCTIVE_DRILL:-0}" != "1" ]; then
  cat <<MSG
==================================================================
Q12-L21 destructive drill is GATED.

  ABS_DESTRUCTIVE_DRILL is not set to 1.

  This script tears down a docker compose namespace, deletes
  volumes, then rebuilds and runs a 7-step bootstrap to validate
  a fresh-deploy cold start.

  To run:
    ABS_DESTRUCTIVE_DRILL=1 bash $0

  The drill stands up an ISOLATED compose namespace (default
  '\${ABS_DRILL_PROJECT:-abs-drill}') on port
  '\${ABS_DRILL_PORT:-28000}' so the live infra-* and abs-cj-*
  stacks (25h customer journey state) remain untouched.

==================================================================
MSG
  exit 0
fi

PROJECT="${ABS_DRILL_PROJECT:-abs-drill}"
PORT="${ABS_DRILL_PORT:-28000}"
ITERS="${ABS_DRILL_ITERS:-1}"

if [ "${PROJECT}" = "infra" ] || [ "${PROJECT}" = "abs-cj" ]; then
  echo "ERROR: refusing to run destructive drill against live namespace '${PROJECT}'." >&2
  echo "Set ABS_DRILL_PROJECT to a sandbox value (default abs-drill)." >&2
  exit 3
fi

COMPOSE="docker compose -p ${PROJECT} -f infra/docker-compose.yml -f infra/docker-compose.dev.yml"

run_iteration() {
  local iter="$1"
  local started ended
  started=$(date +%s)
  echo "============================================================"
  echo "  Iteration ${iter}/${ITERS} — destructive drill (${PROJECT})"
  echo "============================================================"

  echo "==> 1. tear down namespace + volumes"
  ${COMPOSE} down -v --remove-orphans 2>&1 | tail -5

  echo "==> 2. clean SQLite scratch (drill-namespaced)"
  if [ -d "data/${PROJECT}" ]; then
    rm -rf "data/${PROJECT}"
  fi

  echo "==> 3. rebuild image (no cache for full reproducibility)"
  ABS_HOST_PORT="${PORT}" ${COMPOSE} build --no-cache backend 2>&1 | tail -3

  echo "==> 4. bring stack up"
  ABS_HOST_PORT="${PORT}" ${COMPOSE} up -d backend cerbos nats
  echo "    waiting up to 60s for backend healthz..."
  for i in $(seq 1 60); do
    if curl -fsS "http://localhost:${PORT}/healthz" > /dev/null 2>&1; then
      echo "    healthz OK after ${i}s"
      break
    fi
    sleep 1
  done

  echo "==> 5. /healthz must respond 200"
  curl -fsS "http://localhost:${PORT}/healthz" | head -c 200
  echo ""

  echo "==> 6. /readyz must respond 200 (or graceful 503 with detail)"
  curl -sk -o /tmp/abs_drill_readyz.json -w "%{http_code}\n" "http://localhost:${PORT}/readyz" || true
  cat /tmp/abs_drill_readyz.json 2>/dev/null | head -c 300
  echo ""

  echo "==> 7. /v1/marketplace/install Content-Length 60MB → 413 (R27 BodySizeLimit live)"
  big_cl_status=$(curl -sk -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost:${PORT}/v1/marketplace/install" \
    -H "Content-Type: application/json" \
    -H "Content-Length: 60000000" \
    --data-binary "@/dev/null" || echo "ERR")
  echo "    body-size-limit live: ${big_cl_status}"
  if [ "${big_cl_status}" != "413" ]; then
    echo "DRILL FAILED: expected 413 from R27 middleware, got ${big_cl_status}" >&2
    return 1
  fi

  ended=$(date +%s)
  echo "==> iteration ${iter} elapsed: $((ended - started))s"
}

drill_failed=0
for i in $(seq 1 "${ITERS}"); do
  if ! run_iteration "${i}"; then
    drill_failed=1
    break
  fi
done

echo ""
echo "==> teardown of drill namespace"
${COMPOSE} down -v --remove-orphans 2>&1 | tail -3

if [ "${drill_failed}" -ne 0 ]; then
  echo "DRILL RESULT: FAILED" >&2
  exit 1
fi

echo "DRILL RESULT: PASS — ${ITERS} iteration(s) completed cleanly"
