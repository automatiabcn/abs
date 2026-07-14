#!/usr/bin/env bash
# 015 — ABS Manifest signing keypair generator (TEK SEFER, release pipeline kurulumu).
#
# Cikti:
#   ./manifest-keys/private.pem  (BIZIM TARAF — gizli, OFFLINE saklayin)
#   ./manifest-keys/public.pem   (Musteriye gomulecek: app/update/manifest_pubkey.pem)
#
# Sonra:
#   cp manifest-keys/public.pem core/backend/app/update/manifest_pubkey.pem
#   git add core/backend/app/update/manifest_pubkey.pem
#   # Move private.pem to 1Password / hardware token / offline disk — DO NOT put it in the repo

set -euo pipefail

OUT_DIR="${OUT_DIR:-./manifest-keys}"
mkdir -p "$OUT_DIR"

if [ -f "$OUT_DIR/private.pem" ]; then
    echo "WARN: $OUT_DIR/private.pem zaten var. Devam etmek icin elle silin."
    exit 1
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$OUT_DIR/private.pem"
openssl rsa -pubout -in "$OUT_DIR/private.pem" -out "$OUT_DIR/public.pem"
chmod 600 "$OUT_DIR/private.pem"
chmod 644 "$OUT_DIR/public.pem"

echo ""
echo "Generated:"
echo "  Private key (BIZIM, gizli): $OUT_DIR/private.pem"
echo "  Public key (musteri):       $OUT_DIR/public.pem"
echo ""
echo "NEXT:"
echo "  1) cp $OUT_DIR/public.pem core/backend/app/update/manifest_pubkey.pem"
echo "  2) git add core/backend/app/update/manifest_pubkey.pem"
echo "  3) Private key'i offline saklayin (1Password / hardware token / encrypted offsite)"
echo "  4) Repo'ya commit YASAK: $OUT_DIR/private.pem"
echo ""
echo "Release imzalama:"
echo "  openssl dgst -sha256 -sign manifest-keys/private.pem -out manifest.json.sig manifest.json"
echo "  base64 manifest.json.sig > manifest.json.sig.b64"
