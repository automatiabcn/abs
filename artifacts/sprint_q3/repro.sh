#!/usr/bin/env bash
# Sprint Q3 master repro — re-runs the 5 shipped phases (11, 3, 7-code, 2, 8).
# Pre-req: docker compose abs-cj stack healthy.
set -uo pipefail

cd "$(dirname "$0")/../.."
pass=0
fail=0
expect() {
    if [[ "$2" == "$3" ]]; then
        echo "  PASS  $1  ($2)"
        pass=$((pass + 1))
    else
        echo "  FAIL  $1  expected=$2 actual=$3"
        fail=$((fail + 1))
    fi
}

# --- Phase 11: degradation matrix (in-process) ---
echo "=== Phase 11 — degradation matrix ==="
docker exec abs-cj-backend-1 mkdir -p /app/tests/fixtures
docker cp core/backend/tests/fixtures/cascade_degradation_matrix.json \
    abs-cj-backend-1:/app/tests/fixtures/ >/dev/null 2>&1
docker cp artifacts/sprint_q3/phase11_degradation/run_matrix.py \
    abs-cj-backend-1:/tmp/run_matrix.py >/dev/null 2>&1
RC=$(docker exec abs-cj-backend-1 python3 /tmp/run_matrix.py 2>&1 | grep -E "^PASS=" | head -1 | grep -oE "FAIL=[0-9]+" | grep -oE "[0-9]+")
expect "matrix FAIL count" 0 "${RC:-X}"

# --- Phase 3: mock Anthropic fallback ---
echo "=== Phase 3 — mock Anthropic fallback ==="
docker cp artifacts/sprint_q3/phase3_mock_anthropic/run_fallback.py \
    abs-cj-backend-1:/tmp/run_fallback.py >/dev/null 2>&1
RC=$(docker exec abs-cj-backend-1 python3 /tmp/run_fallback.py 2>&1 | grep -E "^PASS=" | head -1 | grep -oE "FAIL=[0-9]+" | grep -oE "[0-9]+")
expect "fallback FAIL count" 0 "${RC:-X}"

# --- Phase 7: groq judge module shipped (live judge needs ABS_GROQ_API_KEY) ---
echo "=== Phase 7 — Groq judge module shipped ==="
SHIPPED=$(docker exec abs-cj-backend-1 python3 -c "
from app.observability.ragas_groq import GroqJudgeBackend, get_groq_evaluator
print('1' if GroqJudgeBackend and get_groq_evaluator else '0')
" 2>/dev/null)
expect "ragas_groq module importable" 1 "$SHIPPED"

# --- Phase 2: signup → magic claim → admin endpoint ---
echo "=== Phase 2 — magic-link multi-admin ==="
EMAIL="repro-q3-$(date +%s)@demo.co"
SLUG="repro-q3-$(date +%s | tail -c 6)"
curl -sk -X POST http://localhost:8000/auth/signup \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"tenant_slug\":\"$SLUG\",\"password\":\"ReproQ32026!\"}" \
    -o /tmp/q3_signup.json -w "" >/dev/null
TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/q3_signup.json'))['magic_link'].split('=')[1])")
[[ "${#TOKEN}" -ge 16 ]] && expect "magic token issued" 1 1 || expect "magic token issued" 1 0

CLAIM=$(curl -sk -c /tmp/q3_session.txt "http://localhost:8000/auth/magic?token=$TOKEN" \
    -o /dev/null -w "%{http_code}")
expect "magic claim 200" 200 "$CLAIM"

ADMIN=$(curl -sk -L -b /tmp/q3_session.txt -o /dev/null -w "%{http_code}" \
    http://localhost:8000/v1/admin/me)
expect "claimed user admin/me 200" 200 "$ADMIN"

# --- Phase 8: A10 lifecycle (uses the user we just claimed) ---
echo "=== Phase 8 — A10 NL workflow lifecycle ==="
RC=$(A10_LOGIN_EMAIL="$EMAIL" A10_LOGIN_PASSWORD="${A10_LOGIN_PASSWORD:-ReproQ32026!}" \
    python3 artifacts/sprint_q3/phase8_a10_workflow/A10_lifecycle.py 2>&1 \
    | grep -E "^A10 PASS=" | grep -oE "FAIL=[0-9]+" | grep -oE "[0-9]+")
expect "A10 FAIL count" 0 "${RC:-X}"

# --- Phase 11 frontend: configured: bool present in quota_status ---
echo "=== Phase 11 — quota.configured wired ==="
CFG=$(curl -sk -L -b /tmp/q3_session.txt http://localhost:8000/v1/system/quota_status \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(int('configured' in d['claude_plus']))")
expect "quota.configured key present" 1 "$CFG"

echo
echo "─────────────────────────────────────────"
echo "PASS=$pass  FAIL=$fail"
exit "$fail"
