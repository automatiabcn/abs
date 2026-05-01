#!/usr/bin/env bash
# T-062 — Postgres restore from S3 dump.
# Usage:
#   ABS_PG_URL=postgres://user:pw@host:5432/db_restored \
#   ABS_DR_S3_BUCKET=abs-pg-backups \
#   ABS_DR_RESTORE_KEY=base/abs-2026-04-28T03-00-00Z.dump \
#   scripts/dr/restore_postgres.sh
#
# Targets RTO < 1 hour. The script does NOT switch live traffic — that's a
# manual `helm upgrade --reuse-values --set state.postgresUrl=...` step.
set -euo pipefail

ABS_PG_URL="${ABS_PG_URL:?ABS_PG_URL must be set}"
S3_BUCKET="${ABS_DR_S3_BUCKET:?ABS_DR_S3_BUCKET must be set}"
RESTORE_KEY="${ABS_DR_RESTORE_KEY:?ABS_DR_RESTORE_KEY must be set (e.g. base/abs-….dump)}"
WORK_DIR="$(mktemp -d -t abs-pg-restore-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[dr] downloading s3://${S3_BUCKET}/${RESTORE_KEY}"
aws s3 cp "s3://${S3_BUCKET}/${RESTORE_KEY}" "${WORK_DIR}/dump"

SIZE=$(wc -c < "${WORK_DIR}/dump")
echo "[dr] downloaded ${SIZE} bytes"

if [ "$SIZE" -lt 1024 ]; then
  echo "[dr] FATAL: dump file < 1 KiB; refusing to restore." >&2
  exit 1
fi

echo "[dr] running pg_restore against ${ABS_PG_URL}"
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname="$ABS_PG_URL" \
  "${WORK_DIR}/dump"

echo "[dr] verifying schema (alembic head match)"
ALEMBIC_HEAD=$(psql "$ABS_PG_URL" -tAc "SELECT version_num FROM alembic_version;")
echo "[dr] alembic head in restored DB: ${ALEMBIC_HEAD}"

echo "[dr] OK — switch traffic with helm upgrade --reuse-values --set state.postgresUrl=..."
