#!/usr/bin/env bash
# DR — consistent backup for the DEFAULT (zero-config) ABS deployment.
#
# The default install runs on SQLite (`sqlite:////app/data/abs.db`), not
# Postgres. backup_postgres.sh / the dr-runbook only cover the Postgres/S3
# topology, so a customer on the default stack had no supported backup path
# for the datastore that holds tenants, users, OAuth + the audit chain.
#
# A naive `tar` of the data volume while the container runs can capture a
# torn, half-written page (and un-checkpointed WAL) → a corrupt restore.
# This uses SQLite's online `.backup` API, which takes a transactionally
# consistent snapshot of a LIVE database, then bundles it.
#
# Usage (run on the host, or inside the backend container):
#   ABS_DATA_DIR=/app/data scripts/dr/backup_sqlite.sh
#
# Env:
#   ABS_DATA_DIR     data dir holding abs.db + secrets.yaml (default /app/data)
#   ABS_DB_FILE      explicit DB path (default $ABS_DATA_DIR/abs.db)
#   ABS_BACKUP_DIR   where the bundle lands (default $ABS_DATA_DIR/backups)
#   ABS_DR_S3_BUCKET optional — also upload the bundle to s3://$bucket/sqlite/
#
# NOTE: the age vault key (vault-key/age.key) is intentionally NOT bundled —
# shipping it next to the encrypted secrets would defeat encryption-at-rest.
# Back the vault key up separately and securely (see docs/dr-runbook.md).
set -euo pipefail

ABS_DATA_DIR="${ABS_DATA_DIR:-/app/data}"
ABS_DB_FILE="${ABS_DB_FILE:-${ABS_DATA_DIR}/abs.db}"
ABS_BACKUP_DIR="${ABS_BACKUP_DIR:-${ABS_DATA_DIR}/backups}"
DATE_TAG="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
WORK_DIR="$(mktemp -d -t abs-sqlite-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

if [ ! -f "$ABS_DB_FILE" ]; then
  echo "[dr] FATAL: database not found at ${ABS_DB_FILE}" >&2
  echo "[dr] (set ABS_DATA_DIR / ABS_DB_FILE; default deployment uses /app/data/abs.db)" >&2
  exit 1
fi

# Consistent snapshot of a possibly-live DB. Prefer the sqlite3 CLI; fall back
# to Python's sqlite3 .backup() API when the CLI isn't installed in the image.
snapshot() {  # src dst
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$1" ".backup '$2'"
  else
    python3 - "$1" "$2" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src)
d = sqlite3.connect(dst)
with d:
    s.backup(d)
s.close()
d.close()
PY
  fi
}

integrity_ok() {  # db -> 0 if "ok"
  local out
  if command -v sqlite3 >/dev/null 2>&1; then
    out="$(sqlite3 "$1" 'PRAGMA integrity_check;' | head -1)"
  else
    out="$(python3 - "$1" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(c.execute("PRAGMA integrity_check").fetchone()[0])
PY
)"
  fi
  [ "$out" = "ok" ]
}

echo "[dr] snapshotting ${ABS_DB_FILE} → consistent copy"
snapshot "$ABS_DB_FILE" "${WORK_DIR}/abs.db"

echo "[dr] verifying snapshot integrity"
if ! integrity_ok "${WORK_DIR}/abs.db"; then
  echo "[dr] FATAL: integrity_check failed on snapshot; refusing to bundle." >&2
  exit 1
fi

# A valid SQLite file is at least one page (>= 4096 B); anything smaller is a
# truncated/failed snapshot. (Checked on the snapshot, not the gzip bundle —
# a near-empty DB compresses to a few hundred bytes and would false-positive.)
SNAP_SIZE=$(wc -c < "${WORK_DIR}/abs.db")
if [ "$SNAP_SIZE" -lt 4096 ]; then
  echo "[dr] FATAL: snapshot only ${SNAP_SIZE} B (< 1 SQLite page). Aborting." >&2
  exit 1
fi

# Durable workflow state (optional, 009).
if [ -f "${ABS_DATA_DIR}/workflow_state.db" ]; then
  echo "[dr] including workflow_state.db"
  snapshot "${ABS_DATA_DIR}/workflow_state.db" "${WORK_DIR}/workflow_state.db" || true
fi

# Encrypted secrets (safe to bundle — age-encrypted at rest; key NOT included).
if [ -f "${ABS_DATA_DIR}/secrets.yaml" ]; then
  echo "[dr] including secrets.yaml (encrypted)"
  cp "${ABS_DATA_DIR}/secrets.yaml" "${WORK_DIR}/secrets.yaml"
fi

mkdir -p "$ABS_BACKUP_DIR"
BUNDLE="${ABS_BACKUP_DIR}/abs-sqlite-${DATE_TAG}.tar.gz"
tar -czf "$BUNDLE" -C "$WORK_DIR" .

SIZE=$(wc -c < "$BUNDLE")
echo "[dr] bundle: ${BUNDLE} (${SIZE} bytes)"
if [ "$SIZE" -lt 100 ]; then
  echo "[dr] FATAL: bundle truncated (<100 B). Removing." >&2
  rm -f "$BUNDLE"
  exit 1
fi

if [ -n "${ABS_DR_S3_BUCKET:-}" ]; then
  echo "[dr] uploading to s3://${ABS_DR_S3_BUCKET}/sqlite/$(basename "$BUNDLE")"
  aws s3 cp "$BUNDLE" "s3://${ABS_DR_S3_BUCKET}/sqlite/$(basename "$BUNDLE")" \
    --storage-class STANDARD_IA
fi

echo "[dr] OK — restore with: scripts/dr/restore_sqlite.sh ${BUNDLE}"
