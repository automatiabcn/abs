#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v docker >/dev/null 2>&1 || { echo "HATA: Docker gerekli (https://docs.docker.com/engine/install/)"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "HATA: Docker Compose v2 gerekli"; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[.env oluşturuldu — düzenleyip ABS_DOMAIN / ABS_ADMIN_EMAIL ayarlayın]"
fi

# 013 — Backend image build (init_vault.sh needs image)
docker compose build backend

# 013 — Vault initialize (produces master age key, writes to abs-vault-key volume)
if [ -f scripts/init_vault.sh ]; then
  bash scripts/init_vault.sh
fi

docker compose up -d

echo ""
echo "ABS kuruldu."
echo "  Panel: https://$(grep '^ABS_DOMAIN=' .env | cut -d= -f2)"
echo "  Loglar: docker compose logs -f"
echo ""
echo "ÖNEMLİ: Master vault key'in offsite (şifrelenmiş) yedeğini alın."
echo "  docker run --rm -v abs-server-product_abs-vault-key:/k alpine cat /k/age.key > age.key.backup"
