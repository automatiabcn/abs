from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

from .keys import load_private_key
from .schemas import LicensePayload


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
