#!/usr/bin/env bash
# One version, one command. The release version is stamped in three files —
# core/backend/pyproject.toml, core/backend/app/config.py (what /healthz and
# the update check report) and core/landing/package.json — and by 2026-08 they
# had drifted to three different numbers while git tags held a fourth. The
# release workflow refuses a tag whose stamps disagree (see release.yml
# "Version stamps match the tag"), and this script is how the stamps move.
#
#   ./scripts/bump_version.sh 1.1.0
#   git commit -am "release: v1.1.0" && git tag v1.1.0 && git push origin main v1.1.0
#
# ABS_REPO_ROOT overrides the tree to edit (used by the tests).

set -euo pipefail

V="${1:?usage: bump_version.sh X.Y.Z (no leading v)}"
case "$V" in
  v*) echo "no leading v — the tag carries the v, the stamps do not: $V" >&2; exit 1 ;;
esac
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || { echo "not a semver: $V" >&2; exit 1; }

ROOT="${ABS_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

PYPROJECT="$ROOT/core/backend/pyproject.toml"
CONFIG="$ROOT/core/backend/app/config.py"
PKGJSON="$ROOT/core/landing/package.json"

for f in "$PYPROJECT" "$CONFIG" "$PKGJSON"; do
  [ -f "$f" ] || { echo "missing stamp file: $f" >&2; exit 1; }
done

sed -i.bak -E "s|^version = \"[^\"]+\"|version = \"$V\"|" "$PYPROJECT"
sed -i.bak -E "s|^(    version: str = \")[^\"]+(\")|\\1$V\\2|" "$CONFIG"
sed -i.bak -E "s|(\"version\": \")[^\"]+(\",)|\\1$V\\2|" "$PKGJSON"
rm -f "$PYPROJECT.bak" "$CONFIG.bak" "$PKGJSON.bak"

echo "stamped $V:"
grep -H '^version = ' "$PYPROJECT"
grep -H 'version: str = ' "$CONFIG"
grep -H '"version":' "$PKGJSON" | head -1

echo
echo "next:"
echo "  (cd core/landing && npm install --package-lock-only)   # keep the lockfile honest"
echo "  git commit -am 'release: v$V' && git tag v$V && git push origin main v$V"
