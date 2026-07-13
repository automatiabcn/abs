# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LicensePayload(BaseModel):
    """What a licence says.

    Fields:
        customer_id: who the licence belongs to.
        tier: self-host | team | enterprise.
        seat_count: how many people it covers.
        iat: when it was issued (UTC epoch seconds).
        exp: when it stops being valid (UTC epoch seconds).
        jti: the licence's own id.
        machine_fp: optional — binds the licence to one machine. When set, it is
            compared against the host's live fingerprint on every check and a
            mismatch is refused. Licences issued without it are not bound to a
            machine, and stay valid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: str = Field(..., description="Who the licence belongs to")
    tier: Literal["self-host", "team", "enterprise", "beta"] = Field(
        "self-host", description="Which plan this licence is for"
    )
    seat_count: int = Field(..., ge=1, description="How many people it covers")
    iat: int = Field(..., description="When it was issued (UTC epoch)")
    exp: int = Field(..., description="When it stops being valid (UTC epoch)")
    jti: str = Field(..., description="The licence's own id")
    machine_fp: Optional[str] = Field(
        None, description="Hardware fingerprint binding (SHA-256 hex)"
    )
