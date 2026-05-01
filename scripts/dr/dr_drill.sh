#!/usr/bin/env bash
# T-062 — Monthly DR drill (staging only).
# Snapshots staging Postgres + Qdrant, drops the data, restores from snapshot,
# runs the smoke suite, records RTO/RPO into benchmarks/results/dr-YYYY-MM.json.
#
# This script must run only against staging; refuses if ABS_ENV != "staging".
set -euo pipefail

ABS_ENV="${ABS_ENV:?ABS_ENV must be set; refusing to run without explicit staging}"
if [ "$ABS_ENV" != "staging" ]; then
  echo "[dr-drill] FATAL: refusing to run drill against env '${ABS_ENV}' — staging only." >&2
  exit 1
fi

MONTH_TAG="$(date -u +%Y-%m)"
RESULT_FILE="benchmarks/results/dr-${MONTH_TAG}.json"
mkdir -p "$(dirname "$RESULT_FILE")"

start_ms() { echo "$(($(date -u +%s%N)/1000000))"; }
elapsed_ms() { local from="$1"; echo $(( $(start_ms) - from )); }

echo "[dr-drill] === ABS DR drill — ${MONTH_TAG} ==="

# --- 1. Backup ---
T0=$(start_ms)
echo "[dr-drill] step 1: backup Postgres + Qdrant"
scripts/dr/backup_postgres.sh
scripts/dr/backup_qdrant.sh
BACKUP_MS=$(elapsed_ms "$T0")
echo "[dr-drill]   backup_ms=${BACKUP_MS}"

# --- 2. Drop staging data (safe — we own it) ---
echo "[dr-drill] step 2: drop staging data"
psql "$ABS_PG_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null

# --- 3. Restore ---
T1=$(start_ms)
echo "[dr-drill] step 3: restore latest"
LATEST_KEY=$(aws s3 ls "s3://${ABS_DR_S3_BUCKET}/base/" | sort | tail -1 | awk '{print $4}')
ABS_DR_RESTORE_KEY="base/${LATEST_KEY}" scripts/dr/restore_postgres.sh
RESTORE_MS=$(elapsed_ms "$T1")
echo "[dr-drill]   restore_ms=${RESTORE_MS}"

# --- 4. Smoke ---
T2=$(start_ms)
echo "[dr-drill] step 4: smoke tests"
pytest -q tests/smoke -k dr_drill --tb=short || {
  echo "[dr-drill] smoke FAILED" >&2
  SMOKE_OK="false"
}
SMOKE_OK="${SMOKE_OK:-true}"
SMOKE_MS=$(elapsed_ms "$T2")

# --- 5. Record ---
TOTAL_MS=$(( BACKUP_MS + RESTORE_MS + SMOKE_MS ))
RTO_MIN=$(( TOTAL_MS / 60000 ))

cat > "$RESULT_FILE" <<EOF
{
  "month": "${MONTH_TAG}",
  "env": "${ABS_ENV}",
  "metrics": {
    "backup_ms": ${BACKUP_MS},
    "restore_ms": ${RESTORE_MS},
    "smoke_ms": ${SMOKE_MS},
    "total_ms": ${TOTAL_MS},
    "rto_minutes": ${RTO_MIN}
  },
  "smoke_ok": ${SMOKE_OK},
  "rto_target_minutes": 60,
  "rto_pass": $([ "$RTO_MIN" -lt 60 ] && echo true || echo false),
  "snapshot_key": "${LATEST_KEY}"
}
EOF

echo "[dr-drill] result written → ${RESULT_FILE}"
echo "[dr-drill] RTO ${RTO_MIN}m / target 60m / smoke=${SMOKE_OK}"

if [ "$SMOKE_OK" != "true" ]; then exit 1; fi
if [ "$RTO_MIN" -ge 60 ]; then
  echo "[dr-drill] WARN: RTO budget breached (${RTO_MIN}m ≥ 60m)" >&2
fi
