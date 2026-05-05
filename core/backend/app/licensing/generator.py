from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

from .keys import load_private_key
from .schemas import LicensePayload

logger = logging.getLogger(__name__)

# Q12-R86 — anything above ~25 years is almost certainly a typo or an attack
# trying to mint a perpetual license. Warn loudly so audit catches it.
_EXCESSIVE_VALID_DAYS = 25 * 365


def generate_license(
    customer_id: str,
    tier: str = "self-host",
    seat_count: int = 1,
    valid_days: int = 365,
) -> str:
    """Belirtilen müşteri için RS256 imzalı JWT lisans üretir.

    Args:
        customer_id: Müşteri kimliği (Stripe customer id veya iç id).
        tier: Lisans seviyesi (self-host | team | enterprise).
        seat_count: Seat sayısı (>=1).
        valid_days: Lisans geçerlilik süresi (gün).

    Returns:
        İmzalanmış JWT token (str).
    """
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
    )

    private_key_bytes = load_private_key(settings.private_key_path)

    return jwt.encode(
        payload.model_dump(),
        key=private_key_bytes,
        algorithm="RS256",
    )
