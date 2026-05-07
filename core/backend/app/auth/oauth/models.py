# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-003 — OAuth 2.1 server-side models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class OAuthClient(SQLModel, table=True):
    """Registered OAuth client (confidential or public).

    PKCE is required for *all* clients (OAuth 2.1). For confidential clients
    the secret is verified additionally during token exchange.
    """

    __tablename__ = "oauth_clients"

    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: str = Field(index=True, unique=True, max_length=64)
    client_secret_hash: Optional[str] = Field(default=None, max_length=128)
    name: str = Field(max_length=128, default="")
    redirect_uris: str = Field(default="", description="newline-separated allow-list")
    allowed_scopes: str = Field(default="openid profile", max_length=512)
    is_confidential: bool = Field(default=False)
    created_at: datetime
    revoked_at: Optional[datetime] = Field(default=None)


class OAuthAuthCode(SQLModel, table=True):
    """Short-lived authorization code (S256 PKCE binding)."""

    __tablename__ = "oauth_auth_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True, max_length=64)
    client_id: str = Field(index=True, max_length=64)
    user_subject: str = Field(max_length=128)
    redirect_uri: str = Field(max_length=512)
    scope: str = Field(default="", max_length=512)
    code_challenge: str = Field(max_length=128)
    code_challenge_method: str = Field(default="S256", max_length=8)
    nonce: Optional[str] = Field(default=None, max_length=128)
    extra_claims_json: str = Field(default="{}", max_length=2048)
    issued_at: datetime
    expires_at: datetime
    used_at: Optional[datetime] = Field(default=None, index=True)


class OAuthRefreshToken(SQLModel, table=True):
    """Opaque refresh token, rotated on each /token use (OAuth 2.1)."""

    __tablename__ = "oauth_refresh_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True, max_length=128)
    client_id: str = Field(index=True, max_length=64)
    user_subject: str = Field(max_length=128)
    scope: str = Field(default="", max_length=512)
    extra_claims_json: str = Field(default="{}", max_length=2048)
    issued_at: datetime
    expires_at: datetime
    rotated_to_hash: Optional[str] = Field(default=None, max_length=128)
    revoked_at: Optional[datetime] = Field(default=None)
