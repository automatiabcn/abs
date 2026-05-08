#!/usr/bin/env bash
# Q12 IP-Hardening R3 — Founder release script.
# Builds and pushes the customer-facing Docker images to GitHub Container
# Registry. Customers never see the source — they pull these images via a
# read-only PAT minted per-customer in customer_onboard.sh.
#
# Usage:
#   ./scripts/release.sh 1.0.0
#
# Required env:
#   GHCR_PAT — personal access token with write:packages, OR `gh auth token`
#              must work (gh CLI authenticated as enzoemir1).
#
# Hard gates:
#   - working tree must be clean (no `git status --porcelain` output)
#   - docker buildx must be available
#   - script will exit non-zero if any push fails

set -euo pipefail

VERSION="${1:?version required (e.g. 1.0.0)}"
GHCR_USER="${GHCR_USER:-enzoemir1}"
BACKEND_IMAGE="ghcr.io/${GHCR_USER}/abs-backend"
LANDING_IMAGE="ghcr.io/${GHCR_USER}/abs-landing"

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# 0. Verify clean working tree — a dirty tree means the build hash would
#    not match what's actually in git, and customers' phone-home would
#    later flag the image as tampered.
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree dirty — commit or stash changes before releasing." >&2
  git status --short >&2
  exit 1
fi

GIT_HASH=$(git rev-parse HEAD)
SHORT_HASH=${GIT_HASH:0:12}

# 1. Compute source hash (stable across rebuilds; covers app/**.py).
SOURCE_HASH=$(find core/backend/app -type f -name "*.py" -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | cut -c 1-16)
COMBINED="${SHORT_HASH}-${SOURCE_HASH}"
echo "[release] git=${SHORT_HASH} source=${SOURCE_HASH}"
echo "[release] BUILD_HASH=${COMBINED}"

# 2. ghcr.io login. Prefer explicit GHCR_PAT, fall back to gh CLI token.
if [ -n "${GHCR_PAT:-}" ]; then
  echo "${GHCR_PAT}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
elif command -v gh >/dev/null 2>&1; then
  gh auth token | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
else
  echo "ERROR: neither GHCR_PAT env var nor gh CLI is available." >&2
  exit 1
fi

# 3. Backend image — Cython compile + source strip in production stage.
echo "=== Building ${BACKEND_IMAGE}:${VERSION} ==="
docker buildx build \
  --build-arg "BUILD_HASH=${COMBINED}" \
  --build-arg "ABS_COMPILE_CYTHON=1" \
  --label "org.opencontainers.image.source=https://github.com/${GHCR_USER}/abs" \
  --label "org.opencontainers.image.revision=${GIT_HASH}" \
  --label "org.opencontainers.image.version=${VERSION}" \
  --label "abs.build.hash=${COMBINED}" \
  --tag "${BACKEND_IMAGE}:${VERSION}" \
  --tag "${BACKEND_IMAGE}:latest" \
  --push \
  core/backend

# 4. Landing image — standalone Next.js, no IP to strip but keep parity.
echo "=== Building ${LANDING_IMAGE}:${VERSION} ==="
docker buildx build \
  --label "org.opencontainers.image.source=https://github.com/${GHCR_USER}/abs" \
  --label "org.opencontainers.image.revision=${GIT_HASH}" \
  --label "org.opencontainers.image.version=${VERSION}" \
  --tag "${LANDING_IMAGE}:${VERSION}" \
  --tag "${LANDING_IMAGE}:latest" \
  --push \
  core/landing

# 5. Tag the git release. `|| true` because re-running the script on the
#    same version (after a push retry) should not error out.
git tag "v${VERSION}" 2>/dev/null || echo "[release] git tag v${VERSION} already exists"
git push origin "v${VERSION}" 2>/dev/null || echo "[release] origin already has v${VERSION}"

# 6. Make packages private (idempotent — safe to re-run).
gh api -X PATCH "/users/${GHCR_USER}/packages/container/abs-backend" \
  -f visibility=private >/dev/null 2>&1 \
  || echo "[release] WARN: could not flip abs-backend to private (may need manual step)"
gh api -X PATCH "/users/${GHCR_USER}/packages/container/abs-landing" \
  -f visibility=private >/dev/null 2>&1 \
  || echo "[release] WARN: could not flip abs-landing to private (may need manual step)"

cat <<DONE

✅ Released v${VERSION}
   ${BACKEND_IMAGE}:${VERSION}
   ${LANDING_IMAGE}:${VERSION}
   BUILD_HASH=${COMBINED}

Next steps:
  - Verify on https://github.com/${GHCR_USER}?tab=packages
  - Test pull as a customer:
      docker pull ${BACKEND_IMAGE}:${VERSION}
  - Bring up customer stack:
      ABS_VERSION=${VERSION} docker compose -f infra/docker-compose.customer.yml up -d
DONE
