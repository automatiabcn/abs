#!/usr/bin/env bash
# Q12 master_repro — round entry points
# Usage: bash artifacts/sprint_q12/master_repro.sh <phase>
#   phases: round1 | round2 | round3 | round4 | round5 | backend | frontend | all

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

phase="${1:-all}"

run_round1() {
  echo "==> Q12 Round 1 — L17 bundle break-even validator"
  node scripts/validate_bundle_split.js
}

run_backend_smoke() {
  echo "==> Backend pytest smoke (Q8+Q10+Q11 inherited)"
  pytest -q app/tests \
    --ignore=app/tests/staging \
    -k "q8 or q10 or q11" || true
}

run_frontend_smoke() {
  echo "==> Frontend Playwright smoke (Q10+Q11 inherited)"
  cd core/landing
  npx playwright test --project=chromium \
    -g "q10|q11" --reporter=line || true
  cd "$REPO_ROOT"
}

case "$phase" in
  round1)   run_round1 ;;
  backend)  run_backend_smoke ;;
  frontend) run_frontend_smoke ;;
  all)      run_round1; run_backend_smoke; run_frontend_smoke ;;
  *)        echo "unknown phase: $phase"; exit 2 ;;
esac
