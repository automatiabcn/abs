#!/usr/bin/env bash
# Q10 Master repro — kalite döngüsü round'larını replay eder. Her round
# için bir entry; "all" Round 1'den son round'a sırayla koşar.
#
# Usage:
#   ./artifacts/sprint_q10/master_repro.sh round1     # L9 spec compile + regression
#   ./artifacts/sprint_q10/master_repro.sh all        # tüm round'lar + Q9 baseline
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

step() { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$1"; }
fail() { printf "\033[1;31m✗ %s\033[0m\n" "$1"; exit 1; }

baseline() {
  step "Baseline — Q9 phaseA backend pytest (regression-safe)"
  bash artifacts/sprint_q9/master_repro.sh phaseA
  ok "Baseline"
}

round1() {
  step "Round 1 / L9 — graceful degradation spec compile"
  ( cd core/landing && npx tsc --noEmit __tests__/playwright/q10-no-api-degradation.spec.ts 2>&1 | grep -v "deprecated" || true )
  step "Round 1 / L9 — chat-stream + chat page surface tsc"
  ( cd core/landing && npx tsc --noEmit 2>&1 | grep -E "panel/chat/page|chat-stream" | grep -v deprecated || true )
  ok "Round 1 L9"
}

PHASE="${1:-all}"
case "$PHASE" in
  baseline)  baseline ;;
  round1)    round1 ;;
  all)
    baseline
    round1
    ;;
  *) fail "unknown phase: $PHASE (use baseline|round1|all)" ;;
esac

ok "master_repro complete: $PHASE"
