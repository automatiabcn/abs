#!/usr/bin/env bash
# Q12 IP-Hardening R3 — build the backend image with an embedded hash
# that combines the git short SHA with a deterministic source-tree hash.
#
# Why two hashes:
#   - Git short = traceability to commit
#   - Source SHA = catches uncommitted edits / vendored tampering
#
# The activation server (Cloudflare Worker, founder operates) compares
# the hash sent at /v1/activate to a known-good list. A reverse-engineer
# patching verifier.py post-build will produce a different SOURCE_HASH.
#
# Usage:
#   ./scripts/build_with_hash.sh                  # tag = <hash>
#   ./scripts/build_with_hash.sh prod             # tag = prod (also pushes hash)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
BACKEND_DIR="${REPO_ROOT}/core/backend"

TAG_OVERRIDE="${1:-}"

cd "$REPO_ROOT"

GIT_HASH=$(git rev-parse HEAD)
SOURCE_HASH=$(find "${BACKEND_DIR}/app" -type f -name "*.py" -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | cut -c 1-16)

COMBINED="${GIT_HASH:0:12}-${SOURCE_HASH}"

if [ -n "$TAG_OVERRIDE" ]; then
  IMAGE_TAG="infra-backend:${TAG_OVERRIDE}"
else
  IMAGE_TAG="infra-backend:${COMBINED}"
fi

echo "[build_with_hash] git=${GIT_HASH:0:12} source=${SOURCE_HASH}"
echo "[build_with_hash] BUILD_HASH=${COMBINED}"
echo "[build_with_hash] tag=${IMAGE_TAG}"

docker build \
  --build-arg "BUILD_HASH=${COMBINED}" \
  -t "${IMAGE_TAG}" \
  "${BACKEND_DIR}"

echo "[build_with_hash] done — ${IMAGE_TAG}"
