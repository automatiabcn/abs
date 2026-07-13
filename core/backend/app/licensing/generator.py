# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

from .keys import assert_mint_keypair_pairs, load_private_key
from .schemas import LicensePayload

logger = logging.getLogger(__name__)

# Anything above ~25 years is almost certainly a typo or an attempt to mint a
# perpetual license. Warn loudly so an audit catches it.
_EXCESSIVE_VALID_DAYS = 25 * 365


def generate_license(
    customer_id: str,
    tier: str = "self-host",
    seat_count: int = 1,
    valid_days: int = 365,
    machine_fp: str | None = None,
) -> str:
    """Mint an RS256-signed license JWT for a customer.

    Args:
        customer_id: Customer identity (billing customer id or internal id).
        tier: License tier (self-host | team | enterprise).
        seat_count: Number of seats (>=1).
        valid_days: Validity in days.
        machine_fp: Optional hardware fingerprint (SHA-256 hex). When set, the
            license only verifies on a host with the same fingerprint; ``None``
            leaves it unbound.

    Returns:
        The signed JWT.
    """
    # A private key that does not pair with the image-baked public key would
    # mint licenses this build cannot verify. No-op where no key is baked in.
    assert_mint_keypair_pairs()

    if valid_days > _EXCESSIVE_VALID_DAYS:
        logger.warning(
            "license_excessive_valid_days customer_id=%s valid_days=%d threshold=%d",
            customer_id,
            valid_days,
            _EXCESSIVE_VALID_DAYS,
        )

    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    exp = int((now + timedelta(days=valid_days)).timestamp())
    jti = uuid.uuid4().hex

    payload = LicensePayload(
        customer_id=customer_id,
        tier=tier,
        seat_count=seat_count,
        iat=iat,
        exp=exp,
        jti=jti,
        machine_fp=machine_fp,
    )

    private_key_bytes = load_private_key(settings.private_key_path)

    payload_dict = payload.model_dump()
    if machine_fp is None:
        # Legacy compat: keep the on-wire JWT free of `null` fields so
        # tokens minted before R2 stay byte-identical for unchanged calls.
        payload_dict.pop("machine_fp", None)

    return jwt.encode(
        payload_dict,
        key=private_key_bytes,
        algorithm="RS256",
    )
