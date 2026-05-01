#!/usr/bin/env bash
# Q8 Master repro — replays every phase verification in the order they
# were committed. Exits non-zero on the first failing phase so the
# founder's terminal stops at the broken surface.
#
# Usage:
#   ./artifacts/sprint_q8/master_repro.sh           # run all phases
#   ./artifacts/sprint_q8/master_repro.sh phaseB    # run a specific phase
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

step() { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$1"; }
fail() { printf "\033[1;31m✗ %s\033[0m\n" "$1"; exit 1; }

phaseA() {
  step "Phase A — chat backend pytest (12 tests)"
  ( cd core/backend && .venv/bin/python -m pytest tests/test_q8_chat.py -q --no-header )
  ok "Phase A backend"
}

phaseB() {
  step "Phase B — workflow vitest (12 + 10 tests)"
  ( cd core/landing && npx vitest run __tests__/workflow.test.ts __tests__/WorkflowChatPanel.test.tsx )
  ok "Phase B canvas + W1/W2 fix"
}

phaseNP_smoke() {
  step "Phase N + P — backend route registration"
  ( cd core/backend && \
    ABS_TEST_MODE=1 \
    ABS_SESSION_SECRET=test-secret-32chars-aaaaaaaaaaaaaaaa \
    .venv/bin/python -c "
from app.api import mcp_tokens, claude_code_hooks
assert any(r.path == '/v1/mcp/tokens' for r in mcp_tokens.router.routes)
assert any(r.path == '/v1/hooks/quota-check' for r in claude_code_hooks.router.routes)
print('routes OK')
" )
  ok "Phase N + P routes"
}

phaseO() {
  step "Phase O — Playwright customer journey (headed, 11 step)"
  ( cd core/landing && npx playwright test q8-customer-journey --headed )
  ok "Phase O 11/11 step"
}

PHASE="${1:-all}"
case "$PHASE" in
  phaseA)  phaseA ;;
  phaseB)  phaseB ;;
  phaseNP) phaseNP_smoke ;;
  phaseO)  phaseO ;;
  all)
    phaseA
    phaseB
    phaseNP_smoke
    echo
    echo "▶ Phase O kept manual — run 'phaseO' once docker compose up + login flow are ready."
    ;;
  *) fail "unknown phase: $PHASE (use phaseA|phaseB|phaseNP|phaseO|all)" ;;
esac

ok "master_repro complete: $PHASE"
