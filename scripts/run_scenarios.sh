#!/usr/bin/env bash
# Run the usage-scenario suite, repeatably, without touching your install.
#
# The suite walks a person through a FIRST install: the wizard creates the
# admin, takes the licence, takes the provider key. That only works against a
# server that has never been set up — so a second run against the same state
# hangs on step 1 with no explanation, which is why these scenarios were run
# once and then quietly stopped being run (found 08-01).
#
# This script owns the whole cycle: a throwaway state directory, a backend of
# its own on a port nobody else uses, its own Qdrant collection, the suite,
# and then it puts the backend away. Whatever install you have on :8000 —
# with your keys, your editor session, your indexed workspace — is untouched.
#
#   scripts/run_scenarios.sh                 # all 15
#   scripts/run_scenarios.sh p0-chat         # one, by filename fragment
#
# GROQ_API_KEY is read from the macOS keychain when it is not already set:
# a real answer needs a real key, and the suite refuses to fake one.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${ABS_SCENARIO_PORT:-8001}"
STATE="${ABS_SCENARIO_STATE:-/tmp/abs-scenarios-state}"
LOG="${ABS_SCENARIO_LOG:-/tmp/abs-scenarios-backend.log}"

if [[ -z "${GROQ_API_KEY:-}" ]]; then
    GROQ_API_KEY="$(security find-generic-password -a automatiabcn -s GROQ_API_KEY -w 2>/dev/null || true)"
fi
if [[ -z "${GROQ_API_KEY:-}" ]]; then
    echo "✗ GROQ_API_KEY not set and not in the keychain — the scenarios need a real key." >&2
    exit 1
fi
export GROQ_API_KEY

# The suite needs two services the product needs in production: an
# authorisation PDP and a vector store. Without them the scenarios do not
# report "missing dependency" — they report the PRODUCT as broken
# (forbidden_rag_action, qdrant_unavailable), which is how three real
# scenarios sat red and were read as flaky (08-01). So bring up whatever is
# missing, in containers of our own, and put back exactly what we started.
STARTED_CONTAINERS=()

# name image port healthcheck-url [docker args...] -- [container command...]
# The command matters: started without `--config`, Cerbos comes up healthy on
# its DEFAULT policy set — which contains none of ours — and then denies every
# action. A healthcheck that only proves "the process is listening" let that
# through and cost two scenarios (08-01).
ensure_service() {
    local name="$1" image="$2" port="$3" health="$4"; shift 4
    local docker_args=() cmd=() seen_sep=0
    for a in ${1+"$@"}; do
        if [[ "$a" == "--" ]]; then seen_sep=1; continue; fi
        if [[ $seen_sep -eq 1 ]]; then cmd+=("$a"); else docker_args+=("$a"); fi
    done
    if curl -fsS -o /dev/null --max-time 2 "$health" 2>/dev/null; then
        echo "  ✓ $name already running — left alone"
        return 0
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "  ! $name is not running and Docker is not available." >&2
        echo "    The scenarios that need it will fail HONESTLY, not silently." >&2
        return 1
    fi
    docker rm -f "abs-scenarios-$name" >/dev/null 2>&1 || true
    echo "· starting $name for this run"
    docker run -d --name "abs-scenarios-$name" -p "$port" \
        ${docker_args[@]+"${docker_args[@]}"} "$image" \
        ${cmd[@]+"${cmd[@]}"} >/dev/null || {
        echo "  ! could not start $name" >&2; return 1; }
    STARTED_CONTAINERS+=("abs-scenarios-$name")
    for _ in $(seq 1 30); do
        curl -fsS -o /dev/null --max-time 2 "$health" 2>/dev/null && return 0
        sleep 1
    done
    echo "  ! $name never became healthy" >&2
    return 1
}

# Never share a port with a running install: that is how a scenario run ends
# up writing into somebody's real state.
if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "· port $PORT busy — stopping the previous scenario backend"
    kill "$(lsof -tiTCP:"$PORT" -sTCP:LISTEN)" 2>/dev/null || true
    sleep 2
fi

ensure_service cerbos "ghcr.io/cerbos/cerbos:0.40.0" "3592:3592" \
    "http://localhost:3592/_cerbos/health" \
    -v "$ROOT/infra/cerbos:/etc/cerbos:ro" \
    -- server --config=/etc/cerbos/config.yaml || true
# Qdrant gets a throwaway volume: the scenarios ingest documents, and those
# vectors must not land in whatever collection a real install is using.
ensure_service qdrant "qdrant/qdrant:v1.12.4" "6333:6333" \
    "http://localhost:6333/readyz" || true

echo "▶ fresh scenario backend on :$PORT (state: $STATE)"
(
    cd "$ROOT/core/backend" && \
    ABS_E2E_PORT="$PORT" \
    ABS_E2E_STATE_DIR="$STATE" \
    ABS_QDRANT_DEFAULT_COLLECTION="${ABS_SCENARIO_COLLECTION:-abs_scenarios}" \
    ./scripts/run_e2e_backend.sh > "$LOG" 2>&1
) &
BACKEND_PID=$!

cleanup() {
    echo "▶ stopping the scenario backend"
    for c in ${STARTED_CONTAINERS[@]+"${STARTED_CONTAINERS[@]}"}; do
        echo "  · removing $c (started by this run)"
        docker rm -f "$c" >/dev/null 2>&1 || true
    done
    kill "$BACKEND_PID" 2>/dev/null || true
    # run_e2e_backend.sh execs uvicorn, so the listener may outlive the wrapper.
    local pid
    pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 40); do
    if curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/healthz" 2>/dev/null; then
        break
    fi
    sleep 1
done
if ! curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/healthz" 2>/dev/null; then
    echo "✗ the scenario backend never came up — see $LOG" >&2
    tail -20 "$LOG" >&2
    exit 2
fi
echo "  ✓ up, and it has never been set up — which is what the wizard needs"

cd "$ROOT/core/landing"
# macOS ships bash 3.2, where "${ARGS[@]}" on an empty array trips `set -u`.
ABS_BACKEND_URL="http://127.0.0.1:$PORT" \
ABS_E2E_STATE_DIR="$STATE" \
npx playwright test -c playwright.scenarios.config.ts --reporter=list ${1:+"$@"}
STATUS=$?

echo "▶ scenarios finished with status $STATUS"
exit "$STATUS"
