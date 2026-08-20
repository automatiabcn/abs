# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Device-authorization grant state (RFC 8628 shape).

Kept in its own module (no FastAPI imports) so `app.db.session.init_db` can
import it for `create_all` without pulling the router and its dependencies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class DeviceGrant(SQLModel, table=True):
    """One editor sign-in attempt.

    The device code is stored only as a SHA-256 digest — a database leak must
    not let anyone redeem a pending grant. The short user code is what the
    human sees and approves in the browser; it is worthless without the
    device code the editor holds.
    """

    __tablename__ = "auth_device_grants"

    id: Optional[int] = Field(default=None, primary_key=True)
    device_code_hash: str = Field(index=True, unique=True, max_length=64)
    user_code: str = Field(index=True, max_length=16)
    scopes: str = Field(default="", max_length=512)
    issued_at: datetime
    expires_at: datetime = Field(index=True)
    last_poll_at: Optional[datetime] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    approved_subject: Optional[str] = Field(default=None, max_length=254)
    approved_tenant: Optional[str] = Field(default=None, max_length=64)
    consumed_at: Optional[datetime] = Field(default=None)
