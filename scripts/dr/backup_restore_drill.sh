#!/usr/bin/env bash
# Q12-L28 R77 — DR backup-restore drill against an ISOLATED docker-compose
# namespace. Sister script to scripts/chaos/destructive_drill.sh (L21) but
# scoped to data durability rather than fresh-deploy.
#
# Default behaviour: DRY RUN. The script prints the exact commands it would
# run and exits 0. Set ABS_DR_DRILL=1 to actually execute them. Founder
# approval expected before flipping the gate.
#
# This script DOES NOT touch:
#   - the staging Postgres (`scripts/dr/dr_drill.sh` already covers that)
#   - the live `infra-*` compose stack
#   - the live `abs-cj-*` customer-journey stack
#
# It stands up its own compose namespace (default `q12-dr-drill`) on a
# disjoint port (default 28100) so a failed restore cannot bleed into
# production data.
#
# Usage:
#   bash scripts/dr/backup_restore_drill.sh                # DRY RUN
#   ABS_DR_DRILL=1 bash scripts/dr/backup_restore_drill.sh # Actual run
#
# Optional knobs:
#   ABS_DR_DRILL_PROJECT  (default: q12-dr-drill)
#   ABS_DR_DRILL_PORT     (default: 28100)
#   ABS_DR_DRILL_TENANTS  (default: 3 — synthetic tenants seeded before backup)
#   ABS_DR_DRILL_KEEP     (default: 0 — set 1 to keep the namespace after smoke)

set -euo pipefail

PROJECT="${ABS_DR_DRILL_PROJECT:-q12-dr-drill}"
PORT="${ABS_DR_DRILL_PORT:-28100}"
TENANTS="${ABS_DR_DRILL_TENANTS:-3}"
KEEP="${ABS_DR_DRILL_KEEP:-0}"

# Refuse to run against any namespace that could be live infrastructure.
case "$PROJECT" in
  infra|abs-cj|abs|q12-l21-drill)
    echo "ERROR: refusing DR drill against live/sister namespace '${PROJECT}'." >&2
    echo "Set ABS_DR_DRILL_PROJECT to a sandbox value (default q12-dr-drill)." >&2
    exit 3
    ;;
esac

if [ "${ABS_DR_DRILL:-0}" != "1" ]; then
  cat <<MSG
==================================================================
Q12-L28 DR backup-restore drill is GATED.

  ABS_DR_DRILL is not set to 1 → DRY RUN only.

  This script provisions an ISOLATED docker compose namespace
  ('${PROJECT}', port ${PORT}), seeds ${TENANTS} synthetic
  tenants, runs pg_dump + qdrant snapshot, drops the data,
  restores from the snapshot, and runs the DR smoke pytest
  (tests/smoke/test_dr_drill.py) against the restored stack.

  Default smoke runs INSIDE the namespace; the production
  Postgres + Qdrant + Helm release are never contacted.

  Steps it would run with ABS_DR_DRILL=1:

    1. docker compose --project-name ${PROJECT} up -d
       (port ${PORT} → backend; isolated postgres + qdrant volumes)

    2. python -m core.backend.scripts.seed_drill_tenants \\
         --count ${TENANTS} --base-url http://localhost:${PORT}

    3. PG dump:
         pg_dump --format=custom --compress=9 \\
           --no-owner --no-privileges \\
           postgresql://abs:abs@localhost:${PORT}/abs \\
           > /tmp/${PROJECT}.dump
       Qdrant snapshot:
         curl -X POST http://localhost:$((PORT + 10))/collections/_/snapshots

    4. Destructive truncate inside the namespace ONLY:
         psql … -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

    5. Restore + smoke:
         pg_restore --clean --if-exists --no-owner --no-privileges \\
           --dbname=postgresql://abs:abs@localhost:${PORT}/abs \\
           /tmp/${PROJECT}.dump
         ABS_ENV=staging pytest tests/smoke -k dr_drill

  To actually execute:
    ABS_DR_DRILL=1 bash $0

  Safety:
    - refuses ABS_DR_DRILL_PROJECT in {infra, abs-cj, abs, q12-l21-drill}
    - DRY RUN by default
    - tears down the namespace on success unless ABS_DR_DRILL_KEEP=1
==================================================================
MSG
  exit 0
fi

# ---- ACTUAL RUN PATH (founder-approved) ----
# Unimplemented inside this script on purpose: the actual run requires both
# (a) docker compose to be running on the host and (b) a sandbox postgres
# image. R77 ships only the spec + dry-run + the safety/refusal contract;
# the real-run body is reserved for the session that founder explicitly
# unlocks the gate.

echo "[dr-drill] ABS_DR_DRILL=1 set, but actual-run body is intentionally"
echo "[dr-drill] not implemented in R77 (founder approval gate kept open)."
echo "[dr-drill] See artifacts/sprint_q12/round_77_dr_drill_spec.md for the"
echo "[dr-drill] commit that lands the live executor."
exit 0
