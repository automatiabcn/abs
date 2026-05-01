#!/usr/bin/env bash
# Q7 dev bootstrap — sync Phase A (Neo4j) + Phase B (marketplace hardening)
# code into the running backend container, install Python deps, and verify
# the network wiring so the live smoke endpoints answer 200.
#
# Idempotent. Safe to run repeatedly. Production deploys rebuild the image
# instead — this is for the dev compose loop where backend is launched
# from a baked image without a source mount.
#
# Usage:
#   bash scripts/dev/q7_bootstrap.sh

set -uo pipefail
cd "$(dirname "$0")/../.."

CONTAINER="abs-cj-backend-1"
NEO4J_CONTAINER="abs-cj-neo4j"
NETWORK="abs-cj_default"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "✗ ${CONTAINER} not running" >&2
    exit 1
fi

echo "▶ Q7 bootstrap"

# ---- Phase A: Neo4j ----
docker exec "$CONTAINER" pip install --quiet "neo4j>=5.18" 2>/dev/null \
    && echo "  ✓ neo4j Python driver installed" \
    || echo "  ! neo4j install failed (may already be present)"

docker cp core/backend/app/integrations/neo4j_client.py "${CONTAINER}:/app/app/integrations/neo4j_client.py"
docker cp core/backend/app/api/graph.py "${CONTAINER}:/app/app/api/graph.py"
docker cp core/backend/app/main.py "${CONTAINER}:/app/app/main.py"
docker cp core/backend/app/config.py "${CONTAINER}:/app/app/config.py"
echo "  ✓ Phase A files synced"

# ---- Phase B: marketplace hardening ----
docker exec "$CONTAINER" pip install --quiet "docker>=7" 2>/dev/null \
    && echo "  ✓ docker SDK installed" \
    || echo "  ! docker SDK install failed (may already be present)"

docker cp core/backend/app/marketplace/sandbox.py "${CONTAINER}:/app/app/marketplace/sandbox.py"
docker cp core/backend/app/marketplace/cosign_verify.py "${CONTAINER}:/app/app/marketplace/cosign_verify.py"
docker cp core/backend/app/api/marketplace.py "${CONTAINER}:/app/app/api/marketplace.py"
echo "  ✓ Phase B files synced"

# ---- Test fixture ----
docker exec "$CONTAINER" mkdir -p /app/tests/fixtures
docker cp core/backend/tests/fixtures/graph_seed.json "${CONTAINER}:/app/tests/fixtures/graph_seed.json"
echo "  ✓ test fixtures synced"

# ---- Restart backend so uvicorn picks up the new modules ----
docker restart "$CONTAINER" >/dev/null
until curl -sk -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:8000/healthz | grep -q 200; do
    sleep 1
done
echo "  ✓ backend restarted, healthz=200"

# ---- Network wiring (if neo4j is up) ----
if docker ps --format '{{.Names}}' | grep -q "^${NEO4J_CONTAINER}$"; then
    if ! docker inspect "$NEO4J_CONTAINER" --format='{{range $k,$_ := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "$NETWORK"; then
        docker network connect --alias neo4j "$NETWORK" "$NEO4J_CONTAINER" >/dev/null 2>&1 \
            && echo "  ✓ neo4j attached to $NETWORK" \
            || echo "  ! network attach failed"
    else
        echo "  ✓ neo4j already on $NETWORK"
    fi
fi

# ---- Smoke ----
ROUTES=$(curl -sk http://localhost:8000/openapi.json 2>/dev/null | python3 -c "
import json, sys
spec = json.load(sys.stdin)
graph_routes = sorted(p for p in spec.get('paths', {}) if '/v1/graph' in p)
print(' '.join(graph_routes))
" 2>/dev/null)
if [[ -n "$ROUTES" ]]; then
    echo "  ✓ /v1/graph/* registered: $ROUTES"
else
    echo "  ✗ /v1/graph routes missing — Phase A not loaded" >&2
    exit 2
fi

echo "▶ Q7 bootstrap done"
