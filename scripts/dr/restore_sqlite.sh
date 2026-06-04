#!/usr/bin/env bash
# DR — restore the DEFAULT (SQLite) ABS deployment from a backup_sqlite.sh
# bundle. Companion to backup_sqlite.sh.
#
# Usage:
#   ABS_DATA_DIR=/app/data scripts/dr/restore_sqlite.sh <bundle.tar.gz>
#
# Safety:
#   * STOP the backend first (SQLite single-writer): restore refuses to run
#     when the live DB looks busy unless ABS_DR_FORCE=1.
#   * The current abs.db is copied to abs.db.pre-restore-<DATE> before being
#     overwritten, so a bad restore is itself reversible.
#   * The restored DB is integrity-checked before it replaces the live file.
#
# Env:
#   ABS_DATA_DIR   target data dir (default /app/data)
#   ABS_DR_FORCE   "1" to override the busy-DB guard (you stopped the backend)
set -euo pipefail

BUNDLE="${1:?usage: restore_sqlite.sh <bundle.tar.gz>}"
ABS_DATA_DIR="${ABS_DATA_DIR:-/app/data}"
DATE_TAG="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
WORK_DIR="$(mktemp -d -t abs-sqlite-restore-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

[ -f "$BUNDLE" ] || { echo "[dr] FATAL: bundle not found: ${BUNDLE}" >&2; exit 1; }

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

# Busy-DB guard: a live SQLite writer leaves a -wal/-shm pair. Restoring under
# a running backend can corrupt both copies.
if [ "${ABS_DR_FORCE:-0}" != "1" ] && { [ -f "${ABS_DATA_DIR}/abs.db-wal" ] || [ -f "${ABS_DATA_DIR}/abs.db-shm" ]; }; then
  echo "[dr] FATAL: ${ABS_DATA_DIR}/abs.db looks live (-wal/-shm present)." >&2
  echo "[dr] Stop the backend first, then re-run (or set ABS_DR_FORCE=1)." >&2
  exit 1
fi

echo "[dr] extracting ${BUNDLE}"
tar -xzf "$BUNDLE" -C "$WORK_DIR"
[ -f "${WORK_DIR}/abs.db" ] || { echo "[dr] FATAL: bundle has no abs.db" >&2; exit 1; }

echo "[dr] verifying restored DB integrity before swap"
if ! integrity_ok "${WORK_DIR}/abs.db"; then
  echo "[dr] FATAL: integrity_check failed on bundled abs.db; aborting." >&2
  exit 1
fi

mkdir -p "$ABS_DATA_DIR"
if [ -f "${ABS_DATA_DIR}/abs.db" ]; then
  PRE="${ABS_DATA_DIR}/abs.db.pre-restore-${DATE_TAG}"
  echo "[dr] backing up current DB → ${PRE}"
  cp "${ABS_DATA_DIR}/abs.db" "$PRE"
fi
# Drop any stale WAL/SHM so the restored file is the single source of truth.
rm -f "${ABS_DATA_DIR}/abs.db-wal" "${ABS_DATA_DIR}/abs.db-shm"

echo "[dr] installing restored abs.db"
cp "${WORK_DIR}/abs.db" "${ABS_DATA_DIR}/abs.db"

if [ -f "${WORK_DIR}/workflow_state.db" ]; then
  echo "[dr] restoring workflow_state.db"
  cp "${WORK_DIR}/workflow_state.db" "${ABS_DATA_DIR}/workflow_state.db"
fi
if [ -f "${WORK_DIR}/secrets.yaml" ]; then
  echo "[dr] restoring secrets.yaml (still age-encrypted; needs the vault key)"
  cp "${WORK_DIR}/secrets.yaml" "${ABS_DATA_DIR}/secrets.yaml"
fi

echo "[dr] OK — start the backend and confirm /healthz → 200 (db:up)."
echo "[dr] Reminder: secrets.yaml decrypts only with your separately-stored vault key."
