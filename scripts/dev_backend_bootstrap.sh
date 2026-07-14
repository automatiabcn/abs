#!/usr/bin/env bash
# Q7 backend bootstrap — image rebuild olmadan dev tarafında source güncellemesi için.
# Production deploy backend imajını yeniden build eder; bu script dev iteration için.
#
# Usage:
#   bash scripts/q7_bootstrap.sh

set -euo pipefail
cd "$(dirname "$0")/.."

CONTAINER="abs-cj-backend-1"
NETWORK="abs-cj_default"
SOURCE="core/backend/app"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "✗ ${CONTAINER} not running" >&2
    exit 1
fi

# Q7 Phase A — Neo4j sources
docker cp "$SOURCE/api/graph.py"               "${CONTAINER}:/app/app/api/graph.py"
docker cp "$SOURCE/integrations/neo4j_client.py" "${CONTAINER}:/app/app/integrations/neo4j_client.py"
docker cp "$SOURCE/main.py"                    "${CONTAINER}:/app/app/main.py"
docker cp "$SOURCE/config.py"                  "${CONTAINER}:/app/app/config.py"

# Q7 Phase B — Marketplace hardening
docker cp "$SOURCE/marketplace/sandbox.py"        "${CONTAINER}:/app/app/marketplace/sandbox.py"
docker cp "$SOURCE/marketplace/cosign_verify.py"  "${CONTAINER}:/app/app/marketplace/cosign_verify.py"
docker cp "$SOURCE/api/marketplace.py"            "${CONTAINER}:/app/app/api/marketplace.py"

# Test fixtures (Phase A pytest seed)
docker exec "$CONTAINER" mkdir -p /app/tests/fixtures
docker cp "core/backend/tests/fixtures/graph_seed.json" "${CONTAINER}:/app/tests/fixtures/graph_seed.json"

# Python deps not in baked image (only needed when running this script against
# an older image; rebuilt images already pin neo4j>=5.18 + docker>=7.1).
docker exec "$CONTAINER" pip install --quiet "neo4j>=5.18" "docker>=7.1" 2>/dev/null || true

# Reload uvicorn — SIGHUP first (clean), restart fallback if HUP unsupported.
docker exec "$CONTAINER" sh -c 'kill -HUP 1' 2>/dev/null || docker restart "$CONTAINER" >/dev/null

# Wait for healthz
until curl -sk -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:8000/healthz | grep -q 200; do
    sleep 1
done

# Network wiring (Phase A neo4j needs same network as backend)
NEO4J_CONTAINER="abs-cj-neo4j"
if docker ps --format '{{.Names}}' | grep -q "^${NEO4J_CONTAINER}$"; then
    if ! docker inspect "$NEO4J_CONTAINER" --format='{{range $k,$_ := .NetworkSettings.Networks}}{{$k}} {{end}}' \
        | grep -q "$NETWORK"; then
        docker network connect --alias neo4j "$NETWORK" "$NEO4J_CONTAINER" 2>/dev/null || true
    fi
fi

echo "✓ Q7 bootstrap complete"
