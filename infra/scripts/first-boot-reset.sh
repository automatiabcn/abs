#!/usr/bin/env bash
# Fresh-install hook — purge dev/test fixtures from a customer instance.
#
# Activated when ABS_FRESH_INSTALL=true is set in the customer's .env. It
# runs reset_test_data.py --confirm --purge-rag inside the backend
# container. Bootstrap admin (admin@demo-acme.com) and any paid-tier
# license rows are guarded by the script.
#
# Idempotent: a second run reports total_deleted=0.

set -euo pipefail

if [[ "${ABS_FRESH_INSTALL:-false}" != "true" ]]; then
  echo "[first-boot] ABS_FRESH_INSTALL!=true — fresh-install reset skipped"
  exit 0
fi

COMPOSE_FILE="${ABS_COMPOSE_FILE:-infra/docker-compose.yml}"
BACKEND_SERVICE="${ABS_BACKEND_SERVICE:-backend}"

echo "[first-boot] purging test data via ${BACKEND_SERVICE}…"

docker compose -f "${COMPOSE_FILE}" exec -T "${BACKEND_SERVICE}" \
  python /app/scripts/reset_test_data.py --confirm --purge-rag

echo "[first-boot] done — customer instance is now reset"
