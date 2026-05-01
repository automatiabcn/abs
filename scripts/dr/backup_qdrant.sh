#!/usr/bin/env bash
# T-062 — Qdrant snapshot + S3 archive (per-collection).
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
COLLECTION="${ABS_QDRANT_COLLECTION:-abs_documents}"
S3_BUCKET="${ABS_DR_S3_BUCKET:-abs-qdrant-backups}"
DATE_TAG="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
WORK_DIR="$(mktemp -d -t abs-qdrant-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

AUTH_HEADER=()
if [ -n "$QDRANT_API_KEY" ]; then
  AUTH_HEADER=(-H "api-key: ${QDRANT_API_KEY}")
fi

echo "[dr] requesting snapshot for collection ${COLLECTION}"
SNAP_NAME=$(curl -fsS -X POST "${AUTH_HEADER[@]}" \
  "${QDRANT_URL}/collections/${COLLECTION}/snapshots" | jq -r '.result.name')
echo "[dr] snapshot created: ${SNAP_NAME}"

echo "[dr] downloading"
curl -fsS "${AUTH_HEADER[@]}" \
  "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAP_NAME}" \
  -o "${WORK_DIR}/${SNAP_NAME}"

echo "[dr] uploading to s3://${S3_BUCKET}/${COLLECTION}/${DATE_TAG}/${SNAP_NAME}"
aws s3 cp "${WORK_DIR}/${SNAP_NAME}" \
  "s3://${S3_BUCKET}/${COLLECTION}/${DATE_TAG}/${SNAP_NAME}" \
  --storage-class STANDARD_IA

echo "[dr] cleaning up Qdrant-side snapshot (S3 is the canonical copy)"
curl -fsS -X DELETE "${AUTH_HEADER[@]}" \
  "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAP_NAME}" >/dev/null

echo "[dr] OK"
