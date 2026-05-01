"""025 — Discord webhook notifications (license / refund / health alert).

Env: ABS_DISCORD_WEBHOOK_URL — empty = no-op (boot stays clean).

Public API:
  - notify_license_purchased(jti, email, tier)
  - notify_refund(jti, reason)
  - notify_health_alert(service, error)

All functions:
  - swallow exceptions (no caller code path should fail because of Discord).
  - return True if Discord posted, False on no-op or fail.
  - timeout 5s.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BRAND_COLOR = 0x1E57AC  # ABS blue
_GREEN = 0x10B981
_ORANGE = 0xEA580C
_RED = 0xEF4444


def _post(embed: dict) -> bool:
    """POST single embed to Discord webhook. Returns ok flag."""
    url = settings.discord_webhook_url
    if not url:
        return False
    payload: dict[str, Any] = {"embeds": [embed]}
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(url, json=payload)
        return 200 <= r.status_code < 300
    except Exception as exc:
        logger.info("[discord] webhook post failed: %s", exc)
        return False


def notify_license_purchased(
    *,
    jti: str,
    email: str,
    tier: str,
    seat_count: Optional[int] = None,
) -> bool:
    """New license purchased — green embed."""
    fields = [
        {"name": "JTI", "value": f"`{jti[:16]}…`", "inline": True},
        {"name": "Tier", "value": tier, "inline": True},
    ]
    if seat_count:
        fields.append({"name": "Seats", "value": str(seat_count), "inline": True})
    embed = {
        "title": "🎉 License purchased",
        "description": f"**{email}** completed checkout.",
        "color": _GREEN,
        "fields": fields,
    }
    return _post(embed)


def notify_refund(*, jti: str, reason: str) -> bool:
    """Refund received — orange embed."""
    embed = {
        "title": "💸 Refund processed",
        "description": f"License `{jti[:16]}…` was revoked.",
        "color": _ORANGE,
        "fields": [
            {"name": "Reason", "value": reason, "inline": True},
        ],
    }
    return _post(embed)


def notify_beta_request(*, email: str, name: str = "", use_case: str = "") -> bool:
    """031 — New beta access request received."""
    fields = [
        {"name": "Email", "value": email, "inline": True},
    ]
    if name:
        fields.append({"name": "Name", "value": name, "inline": True})
    if use_case:
        fields.append({"name": "Use case", "value": use_case[:512], "inline": False})
    embed = {
        "title": "📬 Beta access request",
        "description": "A prospect just asked to join the beta queue.",
        "color": _BRAND_COLOR,
        "fields": fields,
    }
    return _post(embed)


def notify_beta_approved(*, license_jti: str, email: str) -> bool:
    """031 — Beta request approved + license issued."""
    embed = {
        "title": "✅ Beta license issued",
        "description": f"**{email}** is now a beta tester.",
        "color": _GREEN,
        "fields": [
            {"name": "JTI", "value": f"`{license_jti[:16]}…`", "inline": True},
            {"name": "Tier", "value": "beta", "inline": True},
        ],
    }
    return _post(embed)


def notify_milestone(*, metric: str, value: int | str) -> bool:
    """031 — Generic milestone (e.g. '10 beta signups', 'first paid customer')."""
    embed = {
        "title": "🏁 Milestone hit",
        "description": f"**{metric}**",
        "color": _BRAND_COLOR,
        "fields": [
            {"name": "Value", "value": str(value), "inline": True},
        ],
    }
    return _post(embed)


def notify_health_alert(*, service: str, error: str) -> bool:
    """Provider/dependency down — red embed."""
    embed = {
        "title": "🚨 Health alert",
        "description": f"`{service}` reporting failure.",
        "color": _RED,
        "fields": [
            {"name": "Error", "value": error[:1024], "inline": False},
        ],
    }
    return _post(embed)
