#!/usr/bin/env bash
# admin credential reset (idempotent). Known state for repro chain.
#
# Seeds admin@demo-acme.local / LocalPass2026! and marks the setup wizard
# as completed so individual sprint repros don't 307 into the wizard or
# 401 on login. Safe to re-run.
#
# Usage:
#   bash scripts/credential_reset.sh

set -euo pipefail
cd "$(dirname "$0")/.."

CONTAINER="${ABS_BACKEND_CONTAINER:-abs-cj-backend-1}"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "✗ ${CONTAINER} not running" >&2
    exit 1
fi

docker exec "$CONTAINER" python -c "
import bcrypt, json, time
from pathlib import Path
data = Path('/app/data')
data.mkdir(parents=True, exist_ok=True)
pw_hash = bcrypt.hashpw(b'LocalPass2026!', bcrypt.gensalt()).decode()
(data / 'admin_credentials.json').write_text(json.dumps({
    'email': 'admin@demo-acme.local',
    'password_hash': pw_hash,
    'created_at': time.time(),
    'tenant_slug': 'default',
    'source': 'credential_reset',
}, ensure_ascii=False))
(data / 'setup_state.json').write_text(json.dumps({
    'completed': True,
    'current_step': 6,
    'completed_steps': ['admin','license','domain','anthropic','providers','test'],
    'started_at': 0,
    'completed_at': 0,
    'lang': 'en',
    'data': {},
}))
print('admin reset OK')
"
