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
#
#    The manifest_pubkey.pem fetch below is intentionally skipped from
#    this gate (it's `*.pem`-gitignored), so the build context can pick
#    it up without dirtying the tree.
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree dirty — commit or stash changes before releasing." >&2
  git status --short >&2
  exit 1
fi

# 0.1 BUG-12 — fetch the founder's manifest pubkey from ai-pc into the
# backend build context so Dockerfile can COPY it into the image at
# /etc/abs/manifest_pubkey.pem. Without this every customer container
# self-generates a keypair on first boot and rejects the founder's
# license mint with "signature invalid".
echo "[release] fetching manifest pubkey from ai-pc..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 ai-pc \
      'cat ~/keys/abs-manifest-signing-public.pem' \
      > core/backend/manifest_pubkey.pem; then
  echo "ERROR: could not fetch manifest pubkey from ai-pc:~/keys/" >&2
  rm -f core/backend/manifest_pubkey.pem
  exit 1
fi
if [ ! -s core/backend/manifest_pubkey.pem ] \
   || ! head -1 core/backend/manifest_pubkey.pem | grep -q "BEGIN PUBLIC KEY"; then
  echo "ERROR: fetched manifest_pubkey.pem looks malformed" >&2
  exit 1
fi
chmod 644 core/backend/manifest_pubkey.pem
echo "[release] manifest pubkey staged ($(wc -c < core/backend/manifest_pubkey.pem) bytes)"

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

# Multi-arch push so customers on x86_64 (Hetzner CX22 / generic Linux VPS)
# AND Apple Silicon (M1/M2/M3/M4 dev boxes) can both `docker pull` without
# `no matching manifest` errors. Override with RELEASE_PLATFORMS=linux/amd64
# for amd64-only builds during emergency releases.
PLATFORMS="${RELEASE_PLATFORMS:-linux/amd64,linux/arm64}"
echo "[release] platforms=${PLATFORMS}"

# 3. Backend image — Cython compile + source strip in production stage.
#    The Dockerfile's builder stage hashes the produced verifier.so and
#    bakes it into /etc/abs.verifier.hash; tamper_check.py reads that
#    file at boot. Patch A (2026-05-08) — pilot Round 5 found the
#    earlier env-var gate silently disabled in production, so the
#    file-based gate now ships in every release image.
echo "=== Building ${BACKEND_IMAGE}:${VERSION} ==="
docker buildx build \
  --platform "${PLATFORMS}" \
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
  --platform "${PLATFORMS}" \
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
