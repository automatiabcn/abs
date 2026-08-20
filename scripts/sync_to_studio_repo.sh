#!/usr/bin/env bash
# Mirror this repository into abs-studio/server/.
#
# `automatiabcn/abs-studio` is the repository the product ships from: the editor
# in `editor/`, the server in `server/`. `server/` is a plain copy of this tree,
# not a submodule, so it only matches reality when somebody copies it — and on
# 2026-08-03 nobody had since the 2nd. A day of work (the download archive, the
# pricing correction, the product rename, the favicon, the dead-host sweep) was
# missing from the repository we release from, and the way it surfaced was a
# founder reading `server/README.md` on GitHub and finding the retired $299
# pricing still there.
#
# Fixing that README alone would have left every other file stale, which is the
# same mistake in a smaller box. So: mirror the whole tree, from the list git
# already maintains.
#
# Using `git ls-files` rather than rsync is deliberate. It copies exactly what
# is committed here — no .env, no .venv, no _research, no scratch output — so
# an internal file cannot reach the release repository by having been left in
# the working directory.
#
#   ./scripts/sync_to_studio_repo.sh            # copy and show the diff
#   ./scripts/sync_to_studio_repo.sh --commit   # copy, commit and push
#
set -euo pipefail

cd "$(dirname "$0")/.."
SRC="$(pwd)"
STUDIO="${ABS_STUDIO_REPO:-$HOME/Main/abs-studio}"
DEST="$STUDIO/server"

[ -d "$STUDIO/.git" ] || { echo "not a git repo: $STUDIO" >&2; exit 1; }

# Refuse to mirror a dirty tree. The point of the mirror is to carry a known
# state; copying uncommitted edits makes the release repo hold something that
# exists nowhere else.
if [ -n "$(git status --porcelain)" ]; then
    echo "this repository has uncommitted changes — commit them first," >&2
    echo "so the mirror carries a state that can be pointed at:" >&2
    git status --short >&2
    exit 1
fi

REV="$(git rev-parse --short HEAD)"

rm -rf "$DEST"
mkdir -p "$DEST"
# git archive walks the index, so it emits exactly the committed tree.
git archive HEAD | tar -x -C "$DEST"

cd "$STUDIO"

# A last check rather than a comforting assumption: nothing internal came along.
LEAKED="$(git status --porcelain server/ | awk '{print $2}' \
    | grep -E '(^|/)(_research|_agent-tasks|\.env$|\.venv|\.localrun|\.audit)' || true)"
if [ -n "$LEAKED" ]; then
    echo "internal files reached the release repo — aborting:" >&2
    echo "$LEAKED" >&2
    exit 1
fi

echo "mirrored $SRC@$REV -> $DEST"
git status --short server/ | head -20
CHANGED="$(git status --porcelain server/ | wc -l | tr -d ' ')"
echo "($CHANGED paths changed)"

[ "${1:-}" = "--commit" ] || { echo; echo "run with --commit to publish"; exit 0; }

[ "$CHANGED" = "0" ] && { echo "nothing to publish"; exit 0; }

git add server/
git commit -q -m "server: mirror abs-server-product@$REV

The server tree here is a copy, so it is only true when someone copies it.
This brings it back in line with the source repository."
git push -q origin HEAD
echo "pushed"
