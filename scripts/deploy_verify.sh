#!/usr/bin/env bash
# production deploy verification — run after worker finalize
set -uo pipefail

PASS=0
FAIL=0

ok() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "=== 1. Backend container has graph.py ==="
if docker exec abs-cj-backend-1 test -f /app/app/api/graph.py; then ok "graph.py in container"; else fail "graph.py missing"; fi
if docker exec abs-cj-backend-1 test -f /app/app/integrations/neo4j_client.py; then ok "neo4j_client.py in container"; else fail "neo4j_client.py missing"; fi
if docker exec abs-cj-backend-1 test -f /app/app/marketplace/sandbox.py; then ok "sandbox.py in container"; else fail "sandbox.py missing"; fi
if docker exec abs-cj-backend-1 test -f /app/app/marketplace/cosign_verify.py; then ok "cosign_verify.py in container"; else fail "cosign_verify.py missing"; fi

echo
echo "=== 2. main.py registers graph router ==="
if docker exec abs-cj-backend-1 grep -q "from app.api import graph" /app/app/main.py 2>/dev/null; then ok "graph router import"; else fail "graph router not imported"; fi
if docker exec abs-cj-backend-1 grep -qE "include_router\(graph" /app/app/main.py 2>/dev/null; then ok "graph router included"; else fail "graph router not included"; fi

echo
echo "=== 3. /v1/graph/* endpoints LIVE ==="
for ep in cypher ingest nl-query; do
  STATUS=$(curl -sk -o /dev/null -w "%{http_code}" -X POST "http://localhost:8000/v1/graph/$ep" -d '{}' -H "Content-Type: application/json" --max-time 5)
  if [[ "$STATUS" =~ ^(200|400|401|422)$ ]]; then ok "/v1/graph/$ep responds ($STATUS)"; else fail "/v1/graph/$ep = $STATUS (expected 4xx, not 404)"; fi
done

echo
echo "=== 4. host scripts kalıcı ==="
if [ -x scripts/dev_backend_bootstrap.sh ]; then ok "dev_backend_bootstrap.sh executable"; else fail "dev_backend_bootstrap.sh missing"; fi
if [ -x scripts/credential_reset.sh ]; then ok "credential_reset.sh executable"; else fail "credential_reset.sh missing"; fi

echo
echo "=== 5. Neo4j live ingest + cypher ==="
# finalize note: credentials match `scripts/credential_reset.sh` seed
# (admin@demo-acme.local / LocalPass2026!). Earlier draft used a placeholder.
bash scripts/credential_reset.sh >/dev/null 2>&1 || true
# Backend Python image is `python:3.11-slim` — no curl baked in. Drive the
# auth + graph + marketplace probes from the host (port 8000 is dev-mapped).
COOKIE_FILE=/tmp/abs_deploy_verify_cookie.txt
LOGIN=$(curl -sk -c "$COOKIE_FILE" -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.local","password":"LocalPass2026!"}' \
    -o /dev/null -w "%{http_code}")
if [ "$LOGIN" = "200" ] && [ -s "$COOKIE_FILE" ]; then
  ok "auth cookie obtained"

  INGEST=$(curl -sk -b "$COOKIE_FILE" -X POST http://localhost:8000/v1/graph/ingest \
    -H "Content-Type: application/json" \
    -d '{"entities":[{"label":"Person","props":{"id":"test-p1","name":"Test User"}}]}' \
    -o /dev/null -w "%{http_code}")
  if [ "$INGEST" = "200" ]; then ok "graph ingest live"; else fail "graph ingest = $INGEST"; fi

  CYPHER=$(curl -sk -b "$COOKIE_FILE" -X POST http://localhost:8000/v1/graph/cypher \
    -H "Content-Type: application/json" \
    -d '{"cypher":"MATCH (p:Person {id:\"test-p1\"}) RETURN p.name"}' \
    -o /dev/null -w "%{http_code}")
  if [ "$CYPHER" = "200" ]; then ok "graph cypher live"; else fail "graph cypher = $CYPHER"; fi
else
  fail "auth cookie not obtained — credential drift unresolved (login=$LOGIN)"
fi

echo
echo "=== 6. Marketplace install real Docker sandbox ==="
# Reset install ledger so the install path actually invokes PluginSandbox
# instead of returning `already_installed`.
docker exec abs-cj-backend-1 rm -f /app/data/marketplace_installs.json >/dev/null 2>&1 || true
INSTALL=$(curl -sk -b "$COOKIE_FILE" -X POST http://localhost:8000/v1/marketplace/install \
    -H "Content-Type: application/json" \
    -d '{"plugin_id":"slack-receiver"}' \
    -o /dev/null -w "%{http_code}")
if [[ "$INSTALL" =~ ^(200|201)$ ]]; then ok "marketplace install ($INSTALL)"; else fail "install = $INSTALL"; fi

CONTAINERS=$(docker ps --filter "label=abs.plugin" --format "{{.Names}}" | wc -l | tr -d ' ')
if [ "$CONTAINERS" -gt 0 ]; then ok "plugin sandbox container(s) running ($CONTAINERS)"; else fail "no plugin containers (sandbox not real)"; fi

echo
echo "─────────────────────────────────────────"
echo "PASS=$PASS  FAIL=$FAIL"
if [ $FAIL -eq 0 ]; then
  echo "✅ production deploy verified"
  exit 0
else
  echo "❌ production deploy incomplete — $FAIL gap remaining"
  exit 1
fi
