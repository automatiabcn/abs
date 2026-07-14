#!/usr/bin/env bash
# Qdrant snapshot + tarball backup.
#
# Triggers Qdrant snapshot endpoints for every collection, copies the resulting
# files out of the snapshot volume, and tars them with a UTC timestamp.
#
# Required env:
#   QDRANT_URL       (default http://localhost:6333)
#   QDRANT_API_KEY   (optional)
#   BACKUP_DIR       (default ./backups/qdrant)
#   QDRANT_SNAPSHOT_VOLUME  (docker volume name; default abs-qdrant-snapshots)
#
# Usage:
#   scripts/qdrant_backup.sh                   # snapshot all collections
#   scripts/qdrant_backup.sh abs_documents     # snapshot one collection

set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
BACKUP_DIR="${BACKUP_DIR:-./backups/qdrant}"
SNAPSHOT_VOLUME="${QDRANT_SNAPSHOT_VOLUME:-abs-qdrant-snapshots}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}"

curl_qdrant() {
  if [[ -n "${QDRANT_API_KEY}" ]]; then
    curl -fsSL -H "api-key: ${QDRANT_API_KEY}" "$@"
  else
    curl -fsSL "$@"
  fi
}

list_collections() {
  curl_qdrant "${QDRANT_URL}/collections" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("\n".join(c["name"] for c in d["result"]["collections"]))'
}

snapshot_collection() {
  local col="$1"
  echo "[qdrant-backup] snapshotting ${col}"
  curl_qdrant -X POST "${QDRANT_URL}/collections/${col}/snapshots" >/dev/null
}

if [[ $# -gt 0 ]]; then
  COLLECTIONS=("$@")
else
  mapfile -t COLLECTIONS < <(list_collections)
fi

for col in "${COLLECTIONS[@]}"; do
  [[ -z "${col}" ]] && continue
  snapshot_collection "${col}"
done

# Copy snapshot files off the docker volume into BACKUP_DIR/<ts>.
STAGE="${BACKUP_DIR}/${TS}"
mkdir -p "${STAGE}"
docker run --rm \
  -v "${SNAPSHOT_VOLUME}:/snapshots:ro" \
  -v "$(cd "${STAGE}" && pwd):/out" \
  alpine:3 sh -c 'cp -r /snapshots/. /out/'

TARBALL="${BACKUP_DIR}/qdrant-${TS}.tgz"
tar -czf "${TARBALL}" -C "${BACKUP_DIR}" "${TS}"
rm -rf "${STAGE}"

echo "[qdrant-backup] wrote ${TARBALL}"
