#!/usr/bin/env bash
# T-062 — Postgres logical backup for ABS DR.
# Targets RPO < 15 min (this script runs every 10 min via CronJob; WAL streaming
# handles the gap continuously).
set -euo pipefail

ABS_PG_URL="${ABS_PG_URL:?ABS_PG_URL must be set (postgres://user:pw@host:5432/db)}"
S3_BUCKET="${ABS_DR_S3_BUCKET:-abs-pg-backups}"
S3_PREFIX="${ABS_DR_S3_PREFIX:-base}"
DATE_TAG="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
WORK_DIR="$(mktemp -d -t abs-pg-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[dr] starting Postgres dump → ${WORK_DIR}/abs-${DATE_TAG}.sql.gz"
pg_dump --format=custom --compress=9 \
  --no-owner --no-privileges \
  "$ABS_PG_URL" \
  > "${WORK_DIR}/abs-${DATE_TAG}.dump"

SIZE=$(wc -c < "${WORK_DIR}/abs-${DATE_TAG}.dump")
echo "[dr] dump size: ${SIZE} bytes"

if [ "$SIZE" -lt 1024 ]; then
  echo "[dr] FATAL: dump suspiciously small (<1 KiB). Aborting upload." >&2
  exit 1
fi

echo "[dr] uploading to s3://${S3_BUCKET}/${S3_PREFIX}/abs-${DATE_TAG}.dump"
aws s3 cp "${WORK_DIR}/abs-${DATE_TAG}.dump" \
  "s3://${S3_BUCKET}/${S3_PREFIX}/abs-${DATE_TAG}.dump" \
  --storage-class STANDARD_IA \
  --metadata "abs-rpo-target=15m,abs-source=cronjob"

echo "[dr] OK"
