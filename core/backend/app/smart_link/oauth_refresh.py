# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""OAuth refresh token rotation.

`refresh_github_token(key_name)`:
  - Reads current refresh_token from DB (decrypted via vault).
  - POSTs to GitHub `/login/oauth/access_token` with grant_type=refresh_token.
  - On success: stores new access token + new refresh token, updates expires_at.
  - On failure (revoked / network): records last_validated_error.

Background scheduler (in-memory, opt-in): scans expiring tokens hourly and refreshes
those within 1h of expiry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlmodel import Session, select

from app.db.models import ConnectedSecret
from app.db.session import get_engine
from app.smart_link.vault_secrets import (
    decrypt_secret,
    encrypt_secret,
    update_validation_status,
)
from app.vault.audit_chain import append_entry

logger = logging.getLogger(__name__)


def _is_expired_or_close(secret: ConnectedSecret, *, lead_minutes: int = 60) -> bool:
    if secret.expires_at is None:
        return False
    exp = secret.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=lead_minutes)
    return exp <= cutoff


def refresh_github_token(
    key_name: str = "github_oauth_token",
    *,
    http_client: Optional[httpx.Client] = None,
) -> dict:
    """Use stored refresh_token to obtain a fresh access_token from GitHub."""
    refresh_key_name = f"{key_name}__refresh"
    refresh_token = decrypt_secret(refresh_key_name)
    if refresh_token is None:
        return {"ok": False, "error": "No refresh token stored"}

    own_client = False
    if http_client is None:
        http_client = httpx.Client(timeout=10.0)
        own_client = True

    # GitHub's refresh_token grant REQUIRES the OAuth app client_id +
    # client_secret (same as the initial code exchange in api/smart_link.py).
    # Omitting them — as this did before — makes GitHub reject every refresh,
    # so stored tokens silently expired and the integration broke. Pull them
    # from settings for parity with the connect flow.
    from app.config import settings

    try:
        r = http_client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": getattr(settings, "github_client_id", ""),
                "client_secret": getattr(settings, "github_client_secret", ""),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if r.status_code != 200:
            update_validation_status(
                key_name=key_name,
                ok=False,
                error=f"refresh HTTP {r.status_code}",
            )
            return {"ok": False, "status": r.status_code}
        data = r.json() if hasattr(r, "json") else {}
        new_access = data.get("access_token") if isinstance(data, dict) else None
        new_refresh = data.get("refresh_token") if isinstance(data, dict) else None
        expires_in = data.get("expires_in") if isinstance(data, dict) else None
    except Exception as exc:
        update_validation_status(
            key_name=key_name, ok=False, error=str(exc)[:200]
        )
        return {"ok": False, "error": str(exc)[:200]}
    finally:
        if own_client:
            http_client.close()

    if not new_access:
        update_validation_status(
            key_name=key_name, ok=False, error="No access_token in refresh response"
        )
        return {"ok": False, "error": "no_access_token"}

    encrypt_secret(key_name=key_name, provider="github", value=new_access)
    if new_refresh:
        encrypt_secret(
            key_name=refresh_key_name, provider="github", value=new_refresh
        )

    new_exp = None
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        new_exp = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        with Session(get_engine()) as db:
            row = db.scalars(
                select(ConnectedSecret).where(
                    ConnectedSecret.key_name == key_name
                )
            ).first()
            if row is not None:
                row.expires_at = new_exp
                db.add(row)
                db.commit()

    update_validation_status(key_name=key_name, ok=True, error=None)
    try:
        append_entry(
            action="token_refresh",
            actor="oauth-refresh",
            target_key=key_name,
            detail="github access_token refreshed",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "access_token_first8": new_access[:8],
        "refresh_token_rotated": new_refresh is not None,
        "expires_at": new_exp.isoformat() if new_exp else None,
    }


def scan_and_refresh(*, lead_minutes: int = 60) -> dict:
    """Background scan: refresh any token expiring within `lead_minutes`."""
    refreshed = 0
    skipped = 0
    failed = 0
    with Session(get_engine()) as db:
        rows = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.provider == "github")
        ).all()
    for row in rows:
        if not _is_expired_or_close(row, lead_minutes=lead_minutes):
            skipped += 1
            continue
        out = refresh_github_token(key_name=row.key_name)
        if out.get("ok"):
            refreshed += 1
        else:
            failed += 1
    return {"refreshed": refreshed, "skipped": skipped, "failed": failed}
