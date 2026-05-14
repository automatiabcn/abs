#!/usr/bin/env bash
# CJ-006 — first-boot RSA keypair + demo license bootstrap.
# Container start'ta /app/data/{public,private}.pem yoksa RSA-2048 üret;
# ek olarak demo_license.jwt yaz (14-gün trial, demo customer).
#
# BUG-12 (2026-05-09) — when the image-baked founder pubkey is present
# at /etc/abs/manifest_pubkey.pem, both the keypair self-generation and
# the demo-license mint are skipped. Production customer images bake
# the founder's pubkey, the founder holds the matching private key on
# ai-pc, and licenses are minted out-of-band via scripts/_mint_license.py.
# Pre-fix every customer container generated its own keypair on first
# boot and rejected the founder's mint with "signature invalid".
set -euo pipefail

DATA_DIR="${ABS_DATA_DIR:-/app/data}"
PUB="${DATA_DIR}/public.pem"
PRIV="${DATA_DIR}/private.pem"
DEMO_JWT="${DATA_DIR}/demo_license.jwt"
MANIFEST_PUB="${ABS_PUBLIC_KEY_PATH:-/etc/abs/manifest_pubkey.pem}"

mkdir -p "${DATA_DIR}"

if [ -f "${MANIFEST_PUB}" ] && [ -s "${MANIFEST_PUB}" ]; then
    echo "[BOOT] image-baked manifest pubkey present (${MANIFEST_PUB}) — skipping keypair self-generation + demo license"
else
    if [ ! -f "${PUB}" ] || [ ! -f "${PRIV}" ]; then
        echo "[BOOT] generating RSA-2048 keypair into ${DATA_DIR}..."
        python - <<PY
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

data_dir = Path("${DATA_DIR}")
data_dir.mkdir(parents=True, exist_ok=True)

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(data_dir / "private.pem").write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
(data_dir / "public.pem").write_bytes(
    key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)
print(f"[BOOT] keypair written: {data_dir/'public.pem'}, {data_dir/'private.pem'}")
PY
    fi

    if [ ! -f "${DEMO_JWT}" ]; then
        echo "[BOOT] generating demo license JWT..."
        python - <<PY
from pathlib import Path
try:
    from app.licensing.generator import generate_license
except Exception as exc:
    print(f"[BOOT] demo license skipped (import error): {exc}")
    raise SystemExit(0)

token = generate_license(
    customer_id="demo",
    tier="self-host",
    seat_count=5,
    valid_days=14,
)
Path("${DEMO_JWT}").write_text(token, encoding="utf-8")
print(f"[BOOT] demo license JWT written: ${DEMO_JWT}")
PY
    fi
fi

# Sprint 2N FAZ C (P0 #2M-026) — when ABS_DATABASE_URL points at Postgres,
# run alembic upgrade head before launching uvicorn. Sprint 2K RLS migration
# (0015_rls_audit_tables) needs to be applied or KVKK defense-in-depth is
# silently bypassed. SQLite path keeps using SQLModel.metadata.create_all
# (called by app startup) — no schema migration needed for the legacy
# single-tenant install.
DB_URL="${ABS_DATABASE_URL:-}"
case "${DB_URL}" in
    postgresql*|postgres*)
        echo "[BOOT] Postgres detected — running alembic upgrade head..."
        if (cd /app && alembic upgrade head); then
            echo "[BOOT] alembic upgrade head OK"
        else
            echo "[BOOT] ERROR — alembic upgrade head failed; refusing to start with stale schema" >&2
            exit 1
        fi
        ;;
    sqlite*|"")
        echo "[BOOT] SQLite (or unset DB URL) — skipping alembic; SQLModel.metadata.create_all on app start"
        ;;
    *)
        echo "[BOOT] WARN — unknown ABS_DATABASE_URL scheme: ${DB_URL%%:*}" >&2
        ;;
esac

exec "$@"
