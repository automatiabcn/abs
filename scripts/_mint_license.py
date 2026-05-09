#!/usr/bin/env python3
# Standalone helper invoked by customer_onboard.sh / mint_and_email.sh.
# Imports app.licensing.generate_license from core/backend without
# requiring a running backend dev container, so founders can mint on any
# machine (Mac/PC/Linux) that has pyjwt + cryptography installed.
#
# Inputs (via env vars to avoid shell-quoting pitfalls):
#   ABS_PRIVATE_KEY_PATH  — RSA PEM path (consumed by app.config Settings)
#   MINT_EMAIL            — customer email / customer_id claim
#   MINT_TIER             — self-host | team | enterprise | beta
#   MINT_SEATS            — int seat count
#   MINT_VALID_DAYS       — int validity window
#   MINT_MACHINE_FP       — optional SHA-256 hex fingerprint (Q12 R1)

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "core" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.licensing import generate_license  # noqa: E402


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"missing env var: {name}")
    return val


def main() -> None:
    email = _required("MINT_EMAIL")
    tier = os.environ.get("MINT_TIER", "self-host")
    seats = int(os.environ.get("MINT_SEATS", "1"))
    days = int(os.environ.get("MINT_VALID_DAYS", "365"))
    mfp = os.environ.get("MINT_MACHINE_FP", "").strip() or None

    token = generate_license(
        email,
        tier=tier,
        seat_count=seats,
        valid_days=days,
        machine_fp=mfp,
    )
    sys.stdout.write(token)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
