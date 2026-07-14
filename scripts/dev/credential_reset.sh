#!/usr/bin/env bash
# Phase D — Credential reset + bootstrap re-seed (defense-in-depth).
#
# Standalone script: re-seeds admin@demo-acme.local + qa@abs.local in the
# running ABS backend container so individual sprint repros don't fail with
# 401 when run outside of `artifacts/sprint_q5/run_full_chain.sh`.
#
# Usage:
#   bash scripts/dev/credential_reset.sh                # default both creds
#   bash scripts/dev/credential_reset.sh demo           # only admin@demo-acme.local
#   bash scripts/dev/credential_reset.sh qa             # only qa@abs.local
#   bash scripts/dev/credential_reset.sh status         # report current state
#
# Idempotent: safe to re-run after volume reset, container restart, or in
# CI between sprints.
set -uo pipefail

CONTAINER="${ABS_BACKEND_CONTAINER:-abs-cj-backend-1}"
MODE="${1:-both}"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "✗ container ${CONTAINER} not running. Start the stack first:"
    echo "    docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d"
    exit 1
fi

seed_admin() {
    local email="$1"
    local password="$2"
    local tenant="$3"
    docker exec "$CONTAINER" python3 -c "
import bcrypt, json, time
from pathlib import Path
data = Path('/app/data')
data.mkdir(parents=True, exist_ok=True)
hash_b = bcrypt.hashpw('$password'.encode(), bcrypt.gensalt()).decode()
(data / 'admin_credentials.json').write_text(json.dumps({
    'email': '$email', 'password_hash': hash_b, 'created_at': time.time(),
    'tenant_slug': '$tenant', 'source': 'q7_phase_d_reset',
}, ensure_ascii=False))
(data / 'setup_state.json').write_text(json.dumps({
    'completed': True, 'current_step': 6,
    'completed_steps': ['admin','license','domain','anthropic','providers','test'],
    'started_at': 0, 'completed_at': 0, 'lang': 'en', 'data': {},
}))
print('seeded:', '$email')
"
}

verify_login() {
    local email="$1"
    local password="$2"
    local code
    code=$(curl -sk -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/auth/login \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$email\",\"password\":\"$password\"}")
    if [[ "$code" == "200" ]]; then
        echo "  ✓ login ok: $email ($code)"
    else
        echo "  ✗ login FAIL: $email ($code)" >&2
        return 1
    fi
}

case "$MODE" in
    demo)
        seed_admin "admin@demo-acme.local" "LocalPass2026!" "default"
        verify_login "admin@demo-acme.local" "LocalPass2026!"
        ;;
    qa)
        seed_admin "qa@abs.local" "QaSprint2026!" "default"
        verify_login "qa@abs.local" "QaSprint2026!"
        ;;
    both)
        seed_admin "admin@demo-acme.local" "LocalPass2026!" "default"
        verify_login "admin@demo-acme.local" "LocalPass2026!"
        # qa@abs.local overwrites the admin_credentials.json file (single-admin
        # store), so we re-seed demo as the LAST one written. Sprint repros that
        # need qa@abs.local call their own seed step.
        ;;
    status)
        docker exec "$CONTAINER" python3 -c "
import json
from pathlib import Path
ac = Path('/app/data/admin_credentials.json')
ss = Path('/app/data/setup_state.json')
if ac.exists():
    d = json.loads(ac.read_text())
    print('admin_credentials.json:')
    print('  email:', d.get('email'))
    print('  source:', d.get('source'))
    print('  tenant:', d.get('tenant_slug'))
else:
    print('admin_credentials.json: ABSENT')
if ss.exists():
    d = json.loads(ss.read_text())
    print('setup_state.json:')
    print('  completed:', d.get('completed'))
    print('  step:', d.get('current_step'))
else:
    print('setup_state.json: ABSENT')
"
        ;;
    *)
        echo "usage: $0 [demo|qa|both|status]" >&2
        exit 2
        ;;
esac
