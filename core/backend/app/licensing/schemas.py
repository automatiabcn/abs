# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LicensePayload(BaseModel):
    """Lisans token'ının payload'ını tanımlar.

    Alanlar:
        customer_id: Lisansın ait olduğu müşterinin kimliği.
        tier: Lisans seviyesi — self-host | team | enterprise.
        seat_count: Lisansın kapsadığı kullanıcı (seat) sayısı.
        iat: Token oluşturma zamanı (UTC epoch saniye).
        exp: Token geçerlilik sonu (UTC epoch saniye).
        jti: Token'ın benzersiz kimliği (JWT ID).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str = Field(..., description="Müşteri kimliği")
    tier: Literal["self-host", "team", "enterprise", "beta"] = Field(
        "self-host", description="Lisans seviyesi"
    )
    seat_count: int = Field(..., ge=1, description="Kullanıcı (seat) sayısı")
    iat: int = Field(..., description="Oluşturma zamanı (UTC epoch)")
    exp: int = Field(..., description="Geçerlilik sonu (UTC epoch)")
    jti: str = Field(..., description="Token benzersiz kimliği")
