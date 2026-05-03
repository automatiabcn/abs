"""026 Modul B — Slack OAuth + minimal channel post.

Endpoints:
  GET  /v1/smart-link/slack/authorize   — OAuth start (DB state, 10min TTL)
  GET  /v1/smart-link/slack/callback    — code → bot token store
  POST /v1/smart-link/slack/post        — {channel, text} post (admin auth)

Bot token only; user tokens are not stored.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api.smart_link import (
    GithubAuthorizeResponse as _AuthResp,
    _check_admin,
    _consume_state,
    _new_state,
)
from app.config import settings
from app.integrations.slack_signing import verify_slack_signature
from app.observability.audit import emit_event  # Q12-L24 sweep 2
from app.smart_link.vault_secrets import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/v1/smart-link/slack", tags=["smart-link-slack"])

# 028 — Slack events_api endpoint (signed webhook)
events_router = APIRouter(prefix="/v1/integrations/slack", tags=["slack-events"])


from fastapi import Request as _Request  # noqa: E402


@events_router.post("/webhook")
async def slack_events_webhook(request: _Request) -> dict:
    """028 — Slack events_api callback. Verifies HMAC signature + replay window."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    ok, reason = verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        timestamp=timestamp,
        body=body,
        signature=signature,
    )
    if not ok:
        # Q12-L24-003 — pre-fix the response body included `reason`
        # (signing_secret_empty | header_missing | timestamp_invalid |
        # timestamp_expired | signature_mismatch). That lets a caller
        # iterate and learn (a) whether the secret is provisioned at all
        # and (b) which check failed — useful for replay tuning. Move the
        # taxonomy into the audit channel and return a generic 401.
        emit_event(
            request,
            action="integrations.slack.webhook.signature",
            outcome="denied",
            reason=reason or "signature_invalid",
            status_code=401,
            provider="slack",
        )
        logger.warning("[slack] webhook rejected: %s", reason)
        raise HTTPException(401, "slack_signature_invalid")

    try:
        import json as _json

        payload = _json.loads(body or b"{}")
    except Exception as exc:
        emit_event(
            request,
            action="integrations.slack.webhook.payload",
            outcome="denied",
            reason="invalid_json",
            status_code=400,
            provider="slack",
            error_class=type(exc).__name__,
        )
        raise HTTPException(400, "Invalid JSON")

    # URL verification handshake
    if isinstance(payload, dict) and payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    event_type = (payload.get("event") or {}).get("type") if isinstance(payload, dict) else None
    return {
        "ok": True,
        "event_type": event_type,
        "received_at": logger.name,
    }
logger = logging.getLogger(__name__)


class SlackAuthorizeRequest(BaseModel):
    redirect_url: str
    client_id: Optional[str] = None


class SlackPostRequest(BaseModel):
    channel: str
    text: str


@router.get("/authorize", response_model=_AuthResp)
async def slack_authorize(
    redirect_url: str = "https://abs.automatiabcn.com/connect",
    client_id: Optional[str] = None,
) -> _AuthResp:
    state = _new_state("slack", redirect_url)
    cid = client_id or "abs_slack_client_skeleton"
    scopes = "chat:write,channels:read"
    authorize_url = (
        f"https://slack.com/oauth/v2/authorize?client_id={cid}"
        f"&scope={scopes}&state={state}"
    )
    return _AuthResp(authorize_url=authorize_url, state=state)


@router.get("/callback")
async def slack_callback(code: str, state: str) -> dict:
    redirect = _consume_state(state, "slack")
    if redirect is None:
        raise HTTPException(400, "Invalid or expired state")

    bot_token: Optional[str] = None
    error: Optional[str] = None
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": "abs_slack_client_skeleton",
                    "client_secret": "abs_slack_secret_skeleton",
                    "code": code,
                },
            )
            if r.status_code == 200:
                data = r.json() if hasattr(r, "json") else {}
                if isinstance(data, dict) and data.get("ok"):
                    bot_token = data.get("access_token") or data.get("bot_token")
                else:
                    error = (data or {}).get("error", "slack_returned_not_ok")
            else:
                error = f"HTTP {r.status_code}"
    except Exception as exc:
        error = str(exc)[:200]

    if bot_token:
        encrypt_secret(
            key_name="slack_bot_token", provider="slack", value=bot_token
        )

    return {
        "ok": bot_token is not None,
        "provider": "slack",
        "code_received": True,
        "token_stored_via_vault": bot_token is not None,
        "redirect_url": redirect,
        "error": error,
    }


@router.post("/post")
async def slack_post(
    body: SlackPostRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _check_admin(authorization)
    token = decrypt_secret("slack_bot_token")
    if token is None:
        raise HTTPException(404, "No Slack token stored — connect first")
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": body.channel, "text": body.text},
            )
            data = r.json() if r.status_code == 200 else {}
        if r.status_code == 200 and data.get("ok"):
            return {"ok": True, "ts": data.get("ts")}
        return {
            "ok": False,
            "status": r.status_code,
            "error": (data or {}).get("error", "unknown"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
