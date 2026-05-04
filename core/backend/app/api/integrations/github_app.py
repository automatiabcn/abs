"""028 Modul B — GitHub App webhook endpoint (skeleton)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.integrations.github_app import verify_webhook_signature_typed
from app.observability.audit import emit_event  # Q12-L24 sweep 2

router = APIRouter(prefix="/v1/integrations/github", tags=["github-app"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def github_app_webhook(request: Request) -> dict:
    """028 — GitHub App webhook receiver. HMAC SHA-256 verify."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    ok, reason = verify_webhook_signature_typed(
        secret=settings.github_app_webhook_secret,
        body=body,
        signature_header=sig,
    )
    if not ok:
        # Q12-L24-008 — distinguish boot-misconfig (signing_secret_empty)
        # from attack signal (signature_mismatch / header_missing).
        # Response body stays generic to avoid leaking which check failed.
        emit_event(
            request,
            action="integrations.github.webhook.signature",
            outcome="denied",
            reason=reason or "signature_invalid",
            status_code=401,
            provider="github",
        )
        raise HTTPException(401, "GitHub signature verification failed")

    try:
        payload = json.loads(body or b"{}")
    except Exception as exc:
        emit_event(
            request,
            action="integrations.github.webhook.payload",
            outcome="denied",
            reason="invalid_json",
            status_code=400,
            provider="github",
            error_class=type(exc).__name__,
        )
        raise HTTPException(400, "Invalid JSON")
    event = request.headers.get("X-GitHub-Event", "unknown")
    return {
        "ok": True,
        "event": event,
        "action": (payload or {}).get("action") if isinstance(payload, dict) else None,
    }
