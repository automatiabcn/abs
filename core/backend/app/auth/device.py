# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Device-authorization grant — the ABS editor's single-identity sign-in.

The desktop editor cannot host a redirect URI and must not embed a login
form, so the classic ``/oauth/authorize`` (authcode+PKCE) flow does not fit.
This is the RFC 8628 shape instead:

    POST /auth/device/start   → {device_code, user_code, verification_uri, …}
    GET  /auth/device         → browser approval page (panel session required)
    POST /auth/device/approve → binds the signed-in user to the user code
    POST /auth/device/poll    → authorization_pending | slow_down | token

The token handed to the editor is a unified editor token — an ``abs_mcp_``
integration token (scope ``all``) — because every engine surface the editor
speaks to (Composer, code graph, notes, hooks) is reached over ``/mcp``.
Poll responses are always HTTP 200 with an ``error`` field while pending,
matching what the abs-account extension parses.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app.auth.device_models import DeviceGrant
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

DEVICE_GRANT_TTL = timedelta(minutes=10)
POLL_INTERVAL_SECONDS = 5
EDITOR_TOKEN_TTL_DAYS = 90
# Unambiguous alphabet (no vowels → no accidental words, no 0/O/1/I).
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"
USER_CODE_LENGTH = 8
# Unauthenticated endpoint — cap outstanding pending grants so a spray
# cannot grow the table unbounded between TTL sweeps.
MAX_PENDING_GRANTS = 500


def _now() -> datetime:
    """UTC-naive timestamp (matches SQLite default datetime storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_device_code(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_user_code() -> str:
    chars = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(USER_CODE_LENGTH))
    return f"{chars[:4]}-{chars[4:]}"


def _normalize_user_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()


class DeviceStartRequest(BaseModel):
    scopes: list[str] = Field(default_factory=list)


class DeviceApproveRequest(BaseModel):
    user_code: str = Field(..., min_length=4, max_length=16)


class DevicePollRequest(BaseModel):
    device_code: str = Field(..., min_length=16, max_length=128)


@router.post("/auth/device/start")
def device_start(
    body: DeviceStartRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> JSONResponse:
    now = _now()
    pending = db.exec(
        select(func.count())
        .select_from(DeviceGrant)
        .where(DeviceGrant.consumed_at.is_(None))  # type: ignore[union-attr]
        .where(DeviceGrant.expires_at > now)
    ).one()
    if int(pending or 0) >= MAX_PENDING_GRANTS:
        return JSONResponse({"error": "temporarily_unavailable"}, status_code=429)

    device_code = secrets.token_urlsafe(32)
    user_code = _new_user_code()
    db.add(
        DeviceGrant(
            device_code_hash=_hash_device_code(device_code),
            user_code=_normalize_user_code(user_code),
            scopes=" ".join(s.strip() for s in body.scopes if s.strip()),
            issued_at=now,
            expires_at=now + DEVICE_GRANT_TTL,
        )
    )
    db.commit()

    base = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": f"{base}/auth/device?user_code={user_code}",
            "interval": POLL_INTERVAL_SECONDS,
            "expires_in": int(DEVICE_GRANT_TTL.total_seconds()),
        }
    )


def _session_subject(request: Request) -> Optional[str]:
    """Subject from a valid, non-revoked ``abs_session`` panel cookie."""
    from app.auth.oauth.routes import _session_principal

    principal = _session_principal(request)
    return principal[0] if principal is not None else None


def _grant_by_user_code(db: Session, user_code: str) -> Optional[DeviceGrant]:
    normalized = _normalize_user_code(user_code)
    if not normalized:
        return None
    return db.exec(
        select(DeviceGrant)
        .where(DeviceGrant.user_code == normalized)
        .where(DeviceGrant.approved_at.is_(None))  # type: ignore[union-attr]
        .where(DeviceGrant.consumed_at.is_(None))  # type: ignore[union-attr]
        .where(DeviceGrant.expires_at > _now())
        .order_by(DeviceGrant.issued_at.desc())  # type: ignore[attr-defined]
    ).first()


@router.post("/auth/device/approve")
def device_approve(
    body: DeviceApproveRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> JSONResponse:
    subject = _session_subject(request)
    if not subject:
        return JSONResponse({"error": "login_required"}, status_code=401)

    grant = _grant_by_user_code(db, body.user_code)
    if grant is None:
        return JSONResponse({"error": "invalid_user_code"}, status_code=404)

    from app.api.chat import _resolve_tenant

    grant.approved_at = _now()
    grant.approved_subject = subject
    grant.approved_tenant = _resolve_tenant(subject)
    db.add(grant)
    db.commit()
    logger.info(
        "device_grant_approved user_code=%s subject=%s", grant.user_code, subject
    )
    return JSONResponse({"ok": True})


def _mint_editor_token(subject: str, tenant: str) -> str:
    """Unified editor token: an ``abs_mcp_`` integration token (scope all),
    recorded in the issuance ledger so the panel can list/revoke it."""
    from app.api.mcp_tokens import _sign, _token_digest
    from app.db.models import MintedTokenRecord
    from app.db.session import get_session_sync

    issued_at = datetime.now(timezone.utc)
    expires_ts = int(issued_at.timestamp()) + EDITOR_TOKEN_TTL_DAYS * 86400
    label = "ABS Editor (device sign-in)"
    token = _sign(
        {
            "v": 1,
            "tenant": tenant,
            "scope": "all",
            "label": label,
            "iat": int(issued_at.timestamp()),
            "exp": expires_ts,
            "actor": subject,
        }
    )
    try:  # ledger is best-effort — never block the sign-in on it
        with get_session_sync() as ledger_db:
            ledger_db.add(
                MintedTokenRecord(
                    token_digest=_token_digest(token),
                    tenant_slug=tenant,
                    label=label,
                    scope="all",
                    issued_by=subject,
                    issued_at=issued_at,
                    expires_at=datetime.fromtimestamp(expires_ts, tz=timezone.utc),
                )
            )
            ledger_db.commit()
    except Exception:  # noqa: BLE001
        logger.info("device_grant token ledger write skipped", exc_info=True)
    return token


@router.post("/auth/device/poll")
def device_poll(
    body: DevicePollRequest,
    db: Session = Depends(get_session),
) -> JSONResponse:
    grant = db.exec(
        select(DeviceGrant).where(
            DeviceGrant.device_code_hash == _hash_device_code(body.device_code)
        )
    ).first()
    if grant is None or grant.consumed_at is not None:
        return JSONResponse({"error": "invalid_grant"})

    now = _now()
    if grant.expires_at <= now:
        return JSONResponse({"error": "expired_token"})

    # RFC 8628 §3.5 — a client polling faster than `interval` gets slow_down.
    if (
        grant.last_poll_at is not None
        and (now - grant.last_poll_at).total_seconds() < POLL_INTERVAL_SECONDS - 1
    ):
        grant.last_poll_at = now
        db.add(grant)
        db.commit()
        return JSONResponse({"error": "slow_down"})
    grant.last_poll_at = now

    if grant.approved_at is None or not grant.approved_subject:
        db.add(grant)
        db.commit()
        return JSONResponse({"error": "authorization_pending"})

    # Approved → single-use redemption.
    grant.consumed_at = now
    db.add(grant)
    db.commit()
    token = _mint_editor_token(
        grant.approved_subject, grant.approved_tenant or "default"
    )
    logger.info(
        "device_grant_redeemed subject=%s tenant=%s",
        grant.approved_subject,
        grant.approved_tenant,
    )
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "scope": "all",
            "account": {
                "id": grant.approved_subject,
                "label": grant.approved_subject,
                "email": grant.approved_subject,
            },
        }
    )


_APPROVAL_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ABS — Approve editor sign-in</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; background: #0b1016; color: #e6edf3;
    font-family: "DM Sans", -apple-system, "Segoe UI", sans-serif;
  }}
  .card {{
    background: #111823; border: 1px solid #1f2b3a; border-radius: 14px;
    padding: 40px 44px; max-width: 420px; text-align: center;
    box-shadow: 0 24px 60px rgba(0,0,0,.45);
  }}
  .brand {{ font-weight: 700; letter-spacing: .04em; margin-bottom: 4px;
    color: #3a9dff; font-size: 15px; }}
  .tagline {{ color: #6b7a8d; font-size: 12px; margin-bottom: 26px; }}
  h1 {{ font-size: 19px; margin: 0 0 10px; }}
  p {{ color: #9aa8b8; font-size: 14px; line-height: 1.5; }}
  input {{
    width: 100%; box-sizing: border-box; text-align: center;
    font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 24px;
    letter-spacing: .18em; padding: 12px; margin: 18px 0 20px;
    background: #0b1016; color: #34d8c4; border: 1px solid #24405a;
    border-radius: 10px; text-transform: uppercase;
  }}
  button {{
    width: 100%; padding: 13px; font-size: 15px; font-weight: 600;
    color: #08131c; background: linear-gradient(135deg, #3a9dff, #34d8c4);
    border: 0; border-radius: 10px; cursor: pointer;
  }}
  button:disabled {{ opacity: .5; cursor: default; }}
  .msg {{ min-height: 22px; margin-top: 16px; font-size: 13px; }}
  .ok {{ color: #34d8c4; }} .err {{ color: #ff6b6b; }}
  a {{ color: #3a9dff; }}
</style>
</head>
<body>
<div class="card">
  <div class="brand">ABS</div>
  <div class="tagline">Automate the chaos</div>
  <h1>Approve editor sign-in</h1>
  <p>Confirm this code matches the one shown in your ABS editor, then approve.</p>
  <input id="code" value="{user_code}" maxlength="9" spellcheck="false" autocomplete="off">
  <button id="go" onclick="approve()">Approve sign-in</button>
  <div class="msg" id="msg"></div>
</div>
<script>
async function approve() {{
  const btn = document.getElementById('go');
  const msg = document.getElementById('msg');
  btn.disabled = true; msg.textContent = ''; msg.className = 'msg';
  try {{
    const res = await fetch('/auth/device/approve', {{
      method: 'POST', credentials: 'same-origin',
      headers: {{'content-type': 'application/json'}},
      body: JSON.stringify({{user_code: document.getElementById('code').value}})
    }});
    if (res.ok) {{
      msg.textContent = 'Approved — return to the ABS editor. You are signed in.';
      msg.className = 'msg ok';
      return;
    }}
    const data = await res.json().catch(() => ({{}}));
    if (res.status === 401) {{
      msg.innerHTML = 'You need to sign in to the ABS panel first — ' +
        '<a href="/" target="_blank">open the panel</a>, log in, then retry here.';
    }} else {{
      msg.textContent = 'Code not found or expired — check the editor and try again.';
    }}
    msg.className = 'msg err';
  }} catch (e) {{
    msg.textContent = 'Cannot reach the ABS server.';
    msg.className = 'msg err';
  }} finally {{
    btn.disabled = false;
  }}
}}
</script>
</body>
</html>
"""


@router.get("/auth/device", include_in_schema=False)
def device_page(user_code: str = Query(default="")) -> HTMLResponse:
    # The code is rendered into an <input value="…"> — restrict it to the
    # user-code alphabet (+ dash) so no markup can be reflected.
    cleaned = _normalize_user_code(user_code)[: USER_CODE_LENGTH]
    if cleaned and not all(c in USER_CODE_ALPHABET for c in cleaned):
        cleaned = ""
    shown = f"{cleaned[:4]}-{cleaned[4:]}" if len(cleaned) > 4 else cleaned
    return HTMLResponse(_APPROVAL_PAGE.format(user_code=shown))


__all__ = ["router"]
