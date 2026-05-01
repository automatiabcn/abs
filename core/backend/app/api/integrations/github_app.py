"""028 Modul B — GitHub App webhook endpoint (skeleton)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.integrations.github_app import verify_webhook_signature

router = APIRouter(prefix="/v1/integrations/github", tags=["github-app"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def github_app_webhook(request: Request) -> dict:
    """028 — GitHub App webhook receiver. HMAC SHA-256 verify."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_webhook_signature(
        secret=settings.github_app_webhook_secret,
        body=body,
        signature_header=sig,
    ):
        raise HTTPException(401, "GitHub signature verification failed")

    try:
        payload = json.loads(body or b"{}")
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    event = request.headers.get("X-GitHub-Event", "unknown")
    return {
        "ok": True,
        "event": event,
        "action": (payload or {}).get("action") if isinstance(payload, dict) else None,
    }
