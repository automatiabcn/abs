#!/usr/bin/env bash
# Build the generic server archive that /download hands out.
#
# This is NOT `build_customer_pkg.sh`. That one builds a per-customer tarball
# carrying their licence and a private pull token, and it exists because the
# images used to be private. They are public now — an anonymous manifest fetch
# from ghcr.io returns 200 — so the archive a stranger downloads works without
# any credential, and the seven-day trial is what gates it.
#
# What goes in is decided by what the compose file bind-mounts, and what stays
# out is decided by who wrote it: `infra/scripts` holds the founder's deploy
# scripts next to the ones the container needs. Shipping deploy_hetzner.sh to a
# customer would hand them our infrastructure, so the list below is explicit
# rather than a wildcard.
#
#   ./scripts/build_server_archive.sh 1.0.4
#
# Output: dist/abs-server-<version>.tar.gz  (+ .sha256)

set -euo pipefail

VERSION="${1:?version required, e.g. 1.0.4}"
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKG="$STAGE/abs-server-$VERSION"
mkdir -p "$PKG"

# The compose the customer runs, under the name compose looks for by default.
cp "$ROOT/infra/docker-compose.customer.yml" "$PKG/docker-compose.yml"
cp "$ROOT/infra/Caddyfile.customer"          "$PKG/Caddyfile"
cp "$ROOT/infra/.env.example"                "$PKG/.env.example"

# Pin the version this archive installs. The compose defaults ABS_VERSION to
# `latest`, so an archive called abs-server-1.0.4 was pulling whatever `latest`
# happened to point at that day — the name on the tin meant nothing, and two
# customers downloading the same file could end up on different builds. A
# download is a fixed artefact; it should install a fixed version.
if grep -q '^ABS_VERSION=' "$PKG/.env.example"; then
    sed -i.bak "s|^ABS_VERSION=.*|ABS_VERSION=$VERSION|" "$PKG/.env.example" && rm -f "$PKG/.env.example.bak"
else
    printf '\n# The version this archive installs.\nABS_VERSION=%s\n' "$VERSION" >> "$PKG/.env.example"
fi
cp -R "$ROOT/infra/cerbos"                   "$PKG/cerbos"

# Only the scripts the running container actually calls. Everything else in
# infra/scripts is ours.
mkdir -p "$PKG/scripts"
for s in validate_install.py purge_deleted_accounts.py purge_webhook_events.py \
         oauth_state_cleanup.py email_tick.py init_vault.sh first-boot-reset.sh; do
    [ -f "$ROOT/infra/scripts/$s" ] && cp "$ROOT/infra/scripts/$s" "$PKG/scripts/$s"
done

# The installer a customer runs. Deliberately not infra/install.sh: that one
# runs `docker compose build backend`, which needs source the customer does not
# have and never will. It would have failed on the first line that mattered.
cat > "$PKG/install.sh" <<'INSTALL'
#!/usr/bin/env bash
# Install ABS Studio's server. Pulls published images — nothing is built here.
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null 2>&1 || {
    echo "Docker is required: https://docs.docker.com/engine/install/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || {
    echo "Docker Compose v2 is required." >&2; exit 1; }

# Fill the .env in rather than handing it back.
#
# The first run used to copy .env.example, print "set ABS_DOMAIN and
# ABS_ADMIN_EMAIL, then run this again" and stop. For someone trying the
# product that is three manual edits and a second command before anything
# happens — and two of the three values the installer can work out for itself.
# A trial should get from download to running in one go.
[ -f .env ] || cp .env.example .env

set_env() {
    if grep -qE "^$1=" .env; then
        grep -v "^$1=" .env > .env.tmp && mv .env.tmp .env
    fi
    printf '%s=%s\n' "$1" "$2" >> .env
}

DOMAIN="$(grep '^ABS_DOMAIN=' .env | cut -d= -f2- || true)"
if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "abs.local" ]; then
    # abs.local is the example's placeholder, not a hostname that resolves.
    DOMAIN=localhost
    set_env ABS_DOMAIN localhost
    echo "Installing for this machine (ABS_DOMAIN=localhost)."
    echo "Put your own domain in .env and re-run if this is a public server."
fi

# Secrets the compose refuses to start without. Generated here rather than
# asked for: a customer who followed the README to the letter still met
# "required variable ABS_DB_PASSWORD is missing a value", which reads like the
# archive is broken. Appended only when absent — regenerating one of these on a
# second run would lock the customer out of their own database.
for secret in ABS_DB_PASSWORD; do
    if ! grep -qE "^${secret}=.+" .env; then
        set_env "$secret" "$(openssl rand -base64 32 | tr -d '\n/+=' | cut -c1-40)"
        echo "Generated $secret."
    fi
done

# The images are published per-architecture, and the versioned tags are
# amd64-only — so pinning one breaks every ARM machine (an Apple Silicon
# laptop, a Hetzner CAX, Graviton). Docker reports that as "no matching
# manifest for linux/arm64/v8", which tells a customer nothing.
#
# This used to stop and ask them to edit .env. It now picks the tag that has a
# build for this machine and says so: being told to go and change a setting so
# the thing can work is not a choice, it is a chore.
VERSION="$(grep '^ABS_VERSION=' .env | cut -d= -f2- || echo latest)"
VERSION="${VERSION:-latest}"
ARCH="$(uname -m)"
case "$ARCH" in aarch64|arm64) PLATFORM=arm64 ;; x86_64|amd64) PLATFORM=amd64 ;; *) PLATFORM="" ;; esac

if [ -n "$PLATFORM" ] && [ "$VERSION" != "latest" ]; then
    if ! docker manifest inspect "ghcr.io/automatiabcn/abs-backend:$VERSION" 2>/dev/null \
         | grep -q "\"architecture\": \"$PLATFORM\""; then
        echo "The $VERSION images have no $PLATFORM build; using latest instead."
        VERSION=latest
        set_env ABS_VERSION latest
    fi
fi

docker compose pull

# The editor's way in is a port on this machine, so check it is free before
# compose does — it fails with "ports are not available ... address already in
# use", which says nothing about what to do. A real install hit this on
# 2026-08-03 because something unrelated was already on 8000.
port_busy() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -i ":$1" -sTCP:LISTEN >/dev/null 2>&1
    else
        return 1   # cannot tell; let compose be the judge
    fi
}

LOCAL_PORT="$(grep '^ABS_LOCAL_PORT=' .env | cut -d= -f2- || true)"
LOCAL_PORT="${LOCAL_PORT:-8000}"
if port_busy "$LOCAL_PORT"; then
    # Move rather than ask. 8000 is a popular port, and telling somebody to go
    # and edit a config file so the install can proceed is a chore the
    # installer can do itself — compose's own message for this is "ports are
    # not available ... address already in use", which is worse still.
    CHOSEN=""
    for candidate in 8010 8020 8030 8040 8050; do
        port_busy "$candidate" || { CHOSEN="$candidate"; break; }
    done
    if [ -z "$CHOSEN" ]; then
        echo "Port $LOCAL_PORT and the fallbacks 8010-8050 are all in use." >&2
        echo "Set ABS_LOCAL_PORT in .env to a free port and run this again." >&2
        exit 1
    fi
    echo "Port $LOCAL_PORT is taken; using $CHOSEN for the editor instead."
    set_env ABS_LOCAL_PORT "$CHOSEN"
    LOCAL_PORT="$CHOSEN"
fi

docker compose up -d

DOMAIN="$(grep '^ABS_DOMAIN=' .env | cut -d= -f2- || echo localhost)"

# Compose reports "Started", which only means the process was launched. On
# 2026-08-03 an install printed "server is up" while the reverse proxy was in a
# crash loop behind it — every other service healthy, nothing reachable, exit
# code 0. So the installer now asks the front door before it makes a claim.
echo
printf 'Waiting for the front door'
for _ in $(seq 1 30); do
    if curl -sk -o /dev/null --max-time 3 "https://$DOMAIN/" 2>/dev/null; then
        echo
        echo "ABS Studio server is up."
        echo "  Panel:  https://$DOMAIN"
        echo "  Logs:   docker compose logs -f"
        echo

        # Tell them the address to give the editor, rather than leaving them to
        # work it out. A tester on 2026-08-03 reached this line and then had to
        # be told, over several messages, which URL to type and where — the
        # installer knew the answer the whole time and did not say it.
        #
        # localhost is deliberately http://…:PORT and not https://localhost:
        # Caddy's certificate for a local install comes from its own CA, which
        # the machine does not trust, and the editor has no way to be told to
        # accept it. Straight to the backend is the one address that works.
        if [ "$DOMAIN" = "localhost" ] || [ "$DOMAIN" = "127.0.0.1" ]; then
            EDITOR_URL="http://localhost:$LOCAL_PORT"
        else
            EDITOR_URL="https://$DOMAIN"
        fi
        # Write the editor's setting rather than dictating it.
        #
        # A tester on 2026-08-03 got as far as here and then needed several
        # messages to learn which URL to type and which file to type it into.
        # The installer knows both. It only ever creates the file — an existing
        # settings.json is the customer's, and silently rewriting it would be a
        # worse trade than printing a line.
        EDITOR_SETTINGS=""
        case "$(uname -s)" in
            Darwin) EDITOR_SETTINGS="$HOME/Library/Application Support/ABS/User/settings.json" ;;
            Linux)  EDITOR_SETTINGS="$HOME/.config/ABS/User/settings.json" ;;
        esac

        if [ -n "$EDITOR_SETTINGS" ] && [ ! -f "$EDITOR_SETTINGS" ]; then
            mkdir -p "$(dirname "$EDITOR_SETTINGS")"
            printf '{\n  "abs.serverUrl": "%s"\n}\n' "$EDITOR_URL" > "$EDITOR_SETTINGS"
            echo "Pointed ABS Studio at this server."
            echo "  $EDITOR_SETTINGS"
        else
            echo "In ABS Studio, set:"
            echo "  abs.serverUrl   $EDITOR_URL"
            if [ -n "$EDITOR_SETTINGS" ]; then
                echo "  (in $EDITOR_SETTINGS — left alone because it already exists)"
            fi
        fi
        echo
        echo "Sign in from the editor's status bar. If that server is older than"
        echo "the editor and the sign-in fails, mint an integration token in the"
        echo "panel and put it in abs.token instead."
        echo
        echo "Your first seven days need no licence key."
        echo "Guide: https://app.automatiabcn.com/docs/install"
        exit 0
    fi
    printf '.'
    sleep 2
done

echo
echo "The services started but https://$DOMAIN is not answering yet." >&2
echo >&2
echo "If this is a public domain, DNS may still be propagating and Caddy may" >&2
echo "still be obtaining a certificate — give it a few minutes." >&2
echo "Otherwise, the reverse proxy is the place to look:" >&2
echo "  docker compose logs caddy --tail 30" >&2
exit 1
INSTALL
chmod +x "$PKG/install.sh"

cat > "$PKG/README.txt" <<EOF
ABS Studio — server $VERSION

  1. Edit .env (ABS_DOMAIN, ABS_ADMIN_EMAIL).
  2. ./install.sh
  3. Open the panel and follow the setup wizard.

The images are pulled from ghcr.io/automatiabcn. The first seven days are a
trial: no licence key, no card.

Guide: https://app.automatiabcn.com/docs/install
EOF

mkdir -p "$OUT"

# Build the same bytes every time. A tarball normally carries mtimes, uids and
# whatever order the filesystem hands back, so two builds of identical content
# produce different checksums — during the 08-03 release the hash changed on
# every rebuild, and the checksum on the download page went stale each time. A
# customer running `shasum -c` against a stale one is told the file was
# tampered with, which is the worst possible way to be wrong.
#
# So: fixed timestamp, fixed ownership, sorted entries, and gzip without its
# own timestamp header (-n). The date is the release's, not today's.
find "$PKG" -exec touch -t 202601010000 {} +
# `-n` is what stops tar recursing into the directory entries find already
# listed. Without it every file was packed two to four times — once on its own
# and once for each parent — which extracts to the right tree and hides itself
# completely unless you list the archive.
( cd "$STAGE" && find "abs-server-$VERSION" -print0 | sort -z \
    | tar -n --uid 0 --gid 0 --uname root --gname root --null -T - -cf - ) \
    | gzip -n -9 > "$OUT/abs-server-$VERSION.tar.gz"
( cd "$OUT" && shasum -a 256 "abs-server-$VERSION.tar.gz" > "abs-server-$VERSION.tar.gz.sha256" )

echo "built: $OUT/abs-server-$VERSION.tar.gz"
cat "$OUT/abs-server-$VERSION.tar.gz.sha256"

# `--publish` uploads and then proves the upload, because the page carries the
# checksum and the size as literals. Rebuilding changed the hash twice during
# the 08-03 release, and each time the live page kept advertising the old one —
# a customer running `shasum -c` would have been told the file was tampered
# with. Publishing by hand is how those two drift apart, so it happens here.
# Refuse to publish an archive that installs a product older than this tree.
#
# Found 2026-08-03 by installing the published archive and reading the setup
# wizard: it was in Turkish and offered a "14-day demo". The source has been in
# English and offered a seven-day trial for weeks. The images explain it —
# `latest` was built on 5 June and the `1.0.4` backend on 16 May, while the
# repository is at today. Everything verified in source this month was absent
# from the artefact a customer downloads, and the download page went live
# pointing at exactly those images.
#
# Nothing warned. The archive builder pins a version, the compose pulls it, and
# no step compares what is inside with what is here. So this one does: publish
# stops when the image predates HEAD, because an archive is a promise that the
# product inside it is the product described outside it.
if [ "${2:-}" = "--publish" ]; then
    HEAD_EPOCH="$(git log -1 --format=%ct 2>/dev/null || echo 0)"
    for image in abs-backend abs-landing; do
        ref="ghcr.io/automatiabcn/$image:$VERSION"
        created="$(docker image inspect "$ref" --format '{{.Created}}' 2>/dev/null || true)"
        [ -n "$created" ] || continue   # not pulled locally; nothing to compare
        # BSD date first (macOS), GNU second (Linux CI). If neither parses it,
        # stop — silently passing is the one outcome this check exists to
        # prevent, and "I could not tell" is not "it is fine".
        img_epoch="$(date -j -f "%Y-%m-%dT%H:%M:%S" "${created%%.*}" +%s 2>/dev/null \
                     || date -d "$created" +%s 2>/dev/null || echo 0)"
        if [ "$img_epoch" -eq 0 ]; then
            echo "could not read the build date of $ref ($created)." >&2
            echo "Refusing to publish rather than assume it is current." >&2
            exit 1
        fi
        if [ "$img_epoch" -lt "$HEAD_EPOCH" ]; then
            echo "$ref was built $(echo "$created" | cut -c1-10), and this tree is at" >&2
            echo "$(git log -1 --format=%cd --date=short). Publishing would ship an" >&2
            echo "archive whose product is older than the code describing it." >&2
            echo >&2
            echo "Rebuild and push the images first, or pass a version whose images" >&2
            echo "are current." >&2
            exit 1
        fi
    done
fi

[ "${2:-}" = "--publish" ] || exit 0

HOST=root@168.119.104.24
REMOTE=/srv/abs-downloads/$VERSION       # what the gateway container serves as
                                         # /srv/downloads — the names differ,
                                         # and uploading to the other one is a
                                         # silent 404.
URL="https://dl.168-119-104-24.nip.io/$VERSION/abs-server-$VERSION.tar.gz"

ssh "$HOST" "mkdir -p $REMOTE"
scp -q "$OUT/abs-server-$VERSION.tar.gz" "$OUT/abs-server-$VERSION.tar.gz.sha256" "$HOST:$REMOTE/"

LOCAL_SHA="$(shasum -a 256 "$OUT/abs-server-$VERSION.tar.gz" | cut -d' ' -f1)"
FETCHED="$(mktemp)"
trap 'rm -f "$FETCHED"' EXIT
code="$(curl -s -o "$FETCHED" -w '%{http_code}' --max-time 120 "$URL")"
[ "$code" = "200" ] || { echo "the published file does not download: HTTP $code" >&2; exit 1; }

REMOTE_SHA="$(shasum -a 256 "$FETCHED" | cut -d' ' -f1)"
[ "$REMOTE_SHA" = "$LOCAL_SHA" ] || {
    echo "what downloads is not what was built:" >&2
    echo "  built:      $LOCAL_SHA" >&2
    echo "  downloaded: $REMOTE_SHA" >&2
    exit 1
}

echo
echo "published and verified: $URL"
echo
echo "core/landing/lib/downloads.ts must say:"
echo "    size: $(wc -c < "$OUT/abs-server-$VERSION.tar.gz" | tr -d ' '),"
echo "    sha256: \"$LOCAL_SHA\","
