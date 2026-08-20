#!/usr/bin/env bash
# Bring the e2e/live backend BACK UP against the EXISTING .e2e-state — the
# already-installed admin, licence, providers and approvals stay as they are.
#
# run_e2e_backend.sh wipes the state on purpose (a fresh install per suite
# run). That is the wrong tool after a code fix: the editor's stored session
# and minted MCP tokens live against this state, and wiping it silently logs
# the product out. This script is the same environment without the wipe.
#
#   core/backend/scripts/resume_e2e_backend.sh        # :8000, existing state
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${ABS_E2E_PORT:-8000}"
STATE="${ABS_E2E_STATE_DIR:-$BACKEND/.e2e-state}"

if [[ ! -f "$STATE/setup_state.json" ]]; then
    echo "✗ $STATE has no setup_state.json — nothing to resume." >&2
    echo "  For a fresh install run run_e2e_backend.sh instead." >&2
    exit 1
fi

export ABS_ENV="development"
export ABS_DATA_DIR="$STATE"
export ABS_DATABASE_URL="sqlite:///$STATE/abs.db"
export ABS_PRIVATE_KEY_PATH="$STATE/private.pem"
export ABS_PUBLIC_KEY_PATH="$STATE/public.pem"
export ABS_TRANSCRIBE_BACKEND="${ABS_TRANSCRIBE_BACKEND:-groq}"

export ABS_AGENT_FS_ROOTS="[\"$STATE/agent-sandbox\"]"
export ABS_AGENT_FS_WRITE_ENABLED="true"
export ABS_AGENT_SHELL_ENABLED="true"

export ABS_EXTERNAL_MCP_ENABLED="true"
export ABS_EXTERNAL_MCP_ALLOW_PRIVATE="true"
export ABS_EXTERNAL_MCP_FEDERATE_TO_MCP="true"

export ABS_QDRANT_URL="${ABS_QDRANT_URL:-http://localhost:6333}"
export ABS_QDRANT_DEFAULT_COLLECTION="${ABS_QDRANT_DEFAULT_COLLECTION:-abs_e2e}"
export ABS_NEO4J_URI="${ABS_NEO4J_URI:-bolt://localhost:7688}"
export ABS_CERBOS_HOST="${ABS_CERBOS_HOST:-http://localhost:3592}"

cd "$STATE"
export PYTHONPATH="$BACKEND"

exec "$BACKEND/.venv/bin/uvicorn" app.main:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning
