"""028 Modul B — GitHub App migration foundation.

Skeleton for GitHub App auth (alternative to OAuth App). The App-based flow:

  1. Build app JWT (RS256, 10-min TTL) signed by App's private key.
  2. POST /app/installations/<id>/access_tokens with that JWT → installation token.
  3. Use installation token to call GitHub API for that org/user.

This file provides the JWT + installation-token helpers and a webhook handler
skeleton. Live token exchange uses httpx (mock-able in tests).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional

import httpx
import jwt as pyjwt

logger = logging.getLogger(__name__)


def generate_app_jwt(*, app_id: str, private_key_pem: str, ttl_seconds: int = 540) -> str:
    """Build an RS256 JWT identifying the GitHub App.

    Args:
      app_id: GitHub App ID (numeric string from App settings)
      private_key_pem: PEM-encoded RSA private key
      ttl_seconds: token lifetime (max 600 per GitHub spec; default 9min)
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # tolerate clock skew
        "exp": now + ttl_seconds,
        "iss": app_id,
    }
    return pyjwt.encode(payload, private_key_pem, algorithm="RS256")


def fetch_installation_token(
    *,
    app_id: str,
    installation_id: str,
    private_key_pem: str,
    http_client: Optional[httpx.Client] = None,
) -> dict:
    """Exchange an App JWT for an installation token.

    Returns: {"token": str, "expires_at": iso8601, "permissions": dict}
    """
    app_jwt = generate_app_jwt(app_id=app_id, private_key_pem=private_key_pem)
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    close_after = False
    if http_client is None:
        http_client = httpx.Client(timeout=10.0)
        close_after = True
    try:
        r = http_client.post(url, headers=headers)
        if r.status_code != 201:
            return {
                "ok": False,
                "status": r.status_code,
                "error": (r.text or "")[:200],
            }
        data = r.json()
        return {
            "ok": True,
            "token": data.get("token"),
            "expires_at": data.get("expires_at"),
            "permissions": data.get("permissions", {}),
        }
    finally:
        if close_after:
            http_client.close()


def verify_webhook_signature(
    *, secret: str, body: bytes, signature_header: str
) -> bool:
    """Verify GitHub `X-Hub-Signature-256` header.

    Format: `sha256=<hex>` where hex = HMAC-SHA256(secret, body).
    """
    if not secret or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---- App manifest ---------------------------------------------------------------

DEFAULT_MANIFEST = {
    "name": "Automatia ABS",
    "url": "https://abs.automatiabcn.com",
    "hook_attributes": {
        "url": "https://abs.automatiabcn.com/v1/integrations/github/webhook",
        "active": True,
    },
    "redirect_url": "https://abs.automatiabcn.com/connect",
    "callback_urls": ["https://abs.automatiabcn.com/v1/smart-link/github/callback"],
    "public": False,
    "default_events": ["push", "pull_request", "installation"],
    "default_permissions": {
        "contents": "read",
        "metadata": "read",
        "pull_requests": "write",
    },
}
