#!/usr/bin/env bash
# CJ-006 — first-boot RSA keypair + demo license bootstrap.
# Container start'ta /app/data/{public,private}.pem yoksa RSA-2048 üret;
# ek olarak demo_license.jwt yaz (14-gün trial, demo customer).
set -euo pipefail

DATA_DIR="${ABS_DATA_DIR:-/app/data}"
PUB="${DATA_DIR}/public.pem"
PRIV="${DATA_DIR}/private.pem"
DEMO_JWT="${DATA_DIR}/demo_license.jwt"

mkdir -p "${DATA_DIR}"

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

exec "$@"
