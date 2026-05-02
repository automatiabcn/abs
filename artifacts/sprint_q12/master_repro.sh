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

run_round3() {
  echo "==> Q12 Round 3 — L18 cold-cache LCP probe"
  echo "    Prereq: backend on :8000 + frontend prod on :3458"
  curl -sk -c /tmp/q12_cookie.txt -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@demo-acme.com","password":"DemoPass2026!"}' \
    -o /dev/null -w "auth %{http_code}\n"
  cd "$REPO_ROOT/core/landing"
  PLAYWRIGHT_BASE_URL=http://localhost:3458 \
    npx playwright test --project=chromium-desktop -g "q12-l18" --reporter=line
  cd "$REPO_ROOT"
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

run_round4() {
  echo "==> Q12 Round 4 — L19 backwards-compat regression"
  source core/backend/.venv/bin/activate
  cd core/backend
  python -m pytest tests/test_q12_l19_backwards_compat.py -v --tb=short
  cd "$REPO_ROOT"
}

case "$phase" in
  round1)   run_round1 ;;
  round3)   run_round3 ;;
  round4)   run_round4 ;;
  backend)  run_backend_smoke ;;
  frontend) run_frontend_smoke ;;
  all)      run_round1; run_round3; run_round4; run_backend_smoke; run_frontend_smoke ;;
  *)        echo "unknown phase: $phase"; exit 2 ;;
esac
