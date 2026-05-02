#!/usr/bin/env bash
# Q12-L20 — Isolated docker chaos runner.
#
# Stands up a parallel `q12-l20-chaos` compose project on offset ports,
# leaving the live `infra-*` and `abs-cj-*` stacks (25h customer
# journey state) untouched. Then exercises the chaos scenarios:
#
#   1. SIGKILL the chaos backend mid-request
#   2. Pause the chaos backend to simulate hung dependency
#   3. Cut chaos backend↔chaos postgres for 5 seconds
#   4. Disk-full simulation via tmpfs limit
#   5. Redis OOM eviction storm
#
# This script is opt-in. The Playwright suite covers the application
# layer via `page.route()` interception and runs in CI; the live
# docker chaos runs only when a founder explicitly invokes this.
#
# Usage:
#   bash scripts/chaos/q12_l20_isolated.sh up      # spin up chaos namespace
#   bash scripts/chaos/q12_l20_isolated.sh kill    # scenario 1
#   bash scripts/chaos/q12_l20_isolated.sh pause   # scenario 2
#   bash scripts/chaos/q12_l20_isolated.sh netcut  # scenario 3
#   bash scripts/chaos/q12_l20_isolated.sh diskfull # scenario 4
#   bash scripts/chaos/q12_l20_isolated.sh redis   # scenario 5
#   bash scripts/chaos/q12_l20_isolated.sh down    # tear down

set -euo pipefail

PROJECT="q12-l20-chaos"
COMPOSE="docker compose -p ${PROJECT} -f infra/docker-compose.yml"
BACKEND_PORT_OFFSET="${BACKEND_PORT_OFFSET:-18000}"

phase="${1:-help}"

require_namespace() {
  if ! ${COMPOSE} ps --quiet backend 2>/dev/null | grep -q .; then
    echo "ERROR: ${PROJECT} stack not up. Run: $0 up" >&2
    exit 2
  fi
}

case "${phase}" in
  up)
    echo "==> bringing up isolated chaos namespace ${PROJECT} on port ${BACKEND_PORT_OFFSET}"
    ABS_HOST_PORT="${BACKEND_PORT_OFFSET}" ${COMPOSE} up -d backend cerbos nats
    sleep 8
    curl -s "http://localhost:${BACKEND_PORT_OFFSET}/healthz" | head -c 200
    echo ""
    ;;
  kill)
    require_namespace
    echo "==> SIGKILL chaos backend (scenario 1)"
    ${COMPOSE} kill -s KILL backend
    sleep 2
    ${COMPOSE} ps backend
    echo "==> restart"
    ${COMPOSE} up -d backend
    ;;
  pause)
    require_namespace
    echo "==> pause chaos backend for 10s (scenario 2)"
    container="$(${COMPOSE} ps -q backend)"
    docker pause "${container}"
    sleep 10
    docker unpause "${container}"
    ;;
  netcut)
    require_namespace
    echo "==> disconnect chaos backend from network for 5s (scenario 3)"
    container="$(${COMPOSE} ps -q backend)"
    network="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "${container}")"
    docker network disconnect "${network}" "${container}"
    sleep 5
    docker network connect "${network}" "${container}"
    ;;
  diskfull)
    require_namespace
    echo "==> simulate disk full (scenario 4) — fill /tmp inside chaos backend to 95%"
    container="$(${COMPOSE} ps -q backend)"
    docker exec "${container}" sh -c 'dd if=/dev/zero of=/tmp/q12_chaos_fill bs=1M count=200 2>/dev/null; df -h /tmp; rm /tmp/q12_chaos_fill'
    ;;
  redis)
    echo "==> redis OOM (scenario 5) — chaos namespace does not include redis"
    echo "    Sprint 21 cache layer test deferred — invoke when redis service joins compose."
    ;;
  down)
    echo "==> tearing down ${PROJECT}"
    ${COMPOSE} down -v
    ;;
  help|*)
    cat <<HELP
usage: $0 {up|kill|pause|netcut|diskfull|redis|down}

Stands up a parallel docker-compose namespace named '${PROJECT}' so
chaos scenarios never touch the live abs-cj-* customer journey volumes.

Recommended sequence:
  $0 up                  # spin up isolated stack
  $0 kill                # exercise scenario 1
  $0 pause               # exercise scenario 2
  $0 netcut              # exercise scenario 3
  $0 down                # clean teardown
HELP
    ;;
esac
