#!/usr/bin/env bash
# 013 — ABS Vault initialization (TEK SEFER, kurulumda).
#
# Master age key olusturur ve `abs-vault-key` Docker volume'una yazar.
# Volume mounts as `:ro` (read-only) on the backend container.
# Master key kayboltursa secrets.yaml decrypt EDILEMEZ → veri kaybi.
#
# Kullanim:
#   bash infra/scripts/init_vault.sh
#   (compose project name farkli ise: VOLUME_NAME=myproj_abs-vault-key bash ...)
#
# Cikti:
#   "Master key olusturuldu: /vault-key/age.key"
#   "Public recipient: age1xxxxx..."

set -euo pipefail

VOLUME_NAME="${VOLUME_NAME:-abs-server-product_abs-vault-key}"
IMAGE_NAME="${IMAGE_NAME:-automatia-abs:latest}"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERR: docker bulunamadi" >&2
    exit 1
fi

# Does the volume already exist?
if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    echo "Volume olusturuluyor: $VOLUME_NAME"
    docker volume create "$VOLUME_NAME"
fi

# Does the image exist?
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "ERR: $IMAGE_NAME bulunamadi. Once 'docker compose build backend' calistir." >&2
    exit 1
fi

# Generate age key with a temporary container
docker run --rm \
    -v "$VOLUME_NAME:/vault-key" \
    --entrypoint sh \
    "$IMAGE_NAME" \
    -c '
if [ -f /vault-key/age.key ]; then
    echo "Master key zaten var: /vault-key/age.key (atlandi)"
    grep "# public key:" /vault-key/age.key || true
    exit 0
fi
age-keygen -o /vault-key/age.key
chmod 600 /vault-key/age.key
echo "Master key olusturuldu: /vault-key/age.key"
echo "Public recipient:"
grep "# public key:" /vault-key/age.key || true
'

echo ""
echo "Vault initialized."
echo "Backend'i baslatabilirsiniz: docker compose up -d backend"
echo ""
echo "ONEMLI: Master key dosyasinin sifrelenmis offsite yedegini alin."
echo "Kayip = secrets.yaml decrypt EDILEMEZ (provider key'leri + license kaybedilir)."
