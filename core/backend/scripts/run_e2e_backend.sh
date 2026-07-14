#!/usr/bin/env bash
# Bring up a backend the end-to-end scenario suite can be pointed at.
#
# The suite's own instructions used to name a script under `.localrun/`, which is
# in .gitignore — so the file existed on exactly one laptop, and anybody else who
# cloned the repo was told to run something they did not have. The scenarios are
# the only tests here that talk to a real backend with a real cascade behind it;
# the thing that starts one belongs in the repo.
#
#   core/backend/scripts/run_e2e_backend.sh          # :8000, throwaway state
#   ABS_E2E_PORT=8001 ...                            # somewhere else
#
# The server comes up EMPTY — no admin, no provider key, nothing installed. The
# suite installs it through the setup wizard, which is the only way to find out
# whether a person who has just downloaded this can get an answer out of it.
#
# State lives in a directory this script owns and wipes, and the process runs
# from inside it, so:
#   * a run never inherits the last one's admin password, keys or approvals; and
#   * the wizard's `.env` write (pydantic reads `.env` relative to the working
#     directory) lands in the throwaway directory instead of editing the `.env`
#     the developer is using for everything else.
set -euo pipefail

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${ABS_E2E_PORT:-8000}"
STATE="${ABS_E2E_STATE_DIR:-$BACKEND/.e2e-state}"

rm -rf "$STATE"
mkdir -p "$STATE/agent-sandbox"
: > "$STATE/.env"

export ABS_ENV="development"
export ABS_DATA_DIR="$STATE"
export ABS_DATABASE_URL="sqlite:///$STATE/abs.db"
export ABS_PRIVATE_KEY_PATH="$STATE/private.pem"
export ABS_PUBLIC_KEY_PATH="$STATE/public.pem"
export ABS_TRANSCRIBE_BACKEND="${ABS_TRANSCRIBE_BACKEND:-groq}"

# The agent scenarios read files, write files and run commands. They get one
# folder, and every write and every command still stops for a human approval —
# which is itself one of the things the suite checks.
export ABS_AGENT_FS_ROOTS="[\"$STATE/agent-sandbox\"]"
export ABS_AGENT_FS_WRITE_ENABLED="true"
export ABS_AGENT_SHELL_ENABLED="true"

# External MCP federation is off by default in the product — connecting to
# someone else's tool server is a decision an operator makes, not a default they
# inherit. The scenario that exercises it therefore has to be given a server that
# allows it, including on a private address, which is where the test one lives.
export ABS_EXTERNAL_MCP_ENABLED="true"
export ABS_EXTERNAL_MCP_ALLOW_PRIVATE="true"
export ABS_EXTERNAL_MCP_FEDERATE_TO_MCP="true"

# Optional services, on their usual local ports. The knowledge and graph
# scenarios need these; when they are absent those specs fail by name rather
# than skipping themselves and reporting green for a feature that never ran.
export ABS_QDRANT_URL="${ABS_QDRANT_URL:-http://localhost:6333}"
# Its own corpus. The database is thrown away between runs and the vector store
# is not, so the suite was reading the previous run's chunks: meeting ids restart
# at 1 on a fresh SQLite file, the vectors are filed under `meeting-<id>`, and a
# silent recording came back marked "indexed" because a *different* meeting with
# the same number had been indexed an hour earlier. (That the two can drift apart
# at all is a real weakness in the product, not just in the harness — the doc id
# is a counter that only the database owns, and the store outlives it.)
export ABS_QDRANT_DEFAULT_COLLECTION="${ABS_QDRANT_DEFAULT_COLLECTION:-abs_e2e}"
export ABS_NEO4J_URI="${ABS_NEO4J_URI:-bolt://localhost:7688}"
export ABS_CERBOS_HOST="${ABS_CERBOS_HOST:-http://localhost:3592}"

# And it starts empty, like the database does. A collection that survives the run
# that made it would hand the next run a corpus it never ingested.
curl -fsS -X DELETE "$ABS_QDRANT_URL/collections/$ABS_QDRANT_DEFAULT_COLLECTION" \
  >/dev/null 2>&1 || true

cd "$STATE"
export PYTHONPATH="$BACKEND"

# A licence, because the scenarios are a *customer's* server.
#
# The seat gate is real now: a trial covers one person, so an install with no
# licence cannot invite anybody — and half of these scenarios are about inviting
# somebody. That is the correct product behaviour and the wrong harness: a server
# with colleagues on it belongs to someone who is paying for them.
#
# Minted here, with this run's own throwaway keypair, and handed to the wizard
# through a file the setup step reads. Nothing is baked into the repository.
"$BACKEND/.venv/bin/python" - <<'PY'
import os
from pathlib import Path

from app.licensing.keys import generate_keypair
from app.licensing.generator import generate_license

priv = os.environ["ABS_PRIVATE_KEY_PATH"]
pub = os.environ["ABS_PUBLIC_KEY_PATH"]
if not Path(priv).is_file():
    generate_keypair(priv, pub)

token = generate_license(
    customer_id="cus_e2e",
    tier="team",
    seat_count=10,
    valid_days=30,
)
Path(os.environ["ABS_DATA_DIR"], "license_key.txt").write_text(token, encoding="utf-8")
print(f"e2e licence minted: team, 10 seats")
PY

exec "$BACKEND/.venv/bin/uvicorn" app.main:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning
