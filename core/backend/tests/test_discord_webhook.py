"""Discord webhook integration."""

from __future__ import annotations

import httpx

from app.config import settings
from app.integrations.discord_webhook import (
    notify_health_alert,
    notify_license_purchased,
    notify_refund,
)


class _FakeResponse:
    def __init__(self, status_code: int = 204):
        self.status_code = status_code


def test_no_op_when_url_empty(monkeypatch):
    """ABS_DISCORD_WEBHOOK_URL empty → no-op, return False."""
    monkeypatch.setattr(settings, "discord_webhook_url", "")

    posted = []

    def _post(self, url, json=None):
        posted.append((url, json))
        return _FakeResponse(204)

    monkeypatch.setattr(httpx.Client, "post", _post)
    ok = notify_license_purchased(jti="jti_test", email="x@y.co", tier="self-host")
    assert ok is False
    assert posted == []


def test_license_purchased_posts_embed(monkeypatch):
    monkeypatch.setattr(
        settings, "discord_webhook_url", "https://discord.com/api/webhooks/test"
    )
    captured: list[dict] = []

    def _post(self, url, json=None):
        captured.append({"url": url, "payload": json})
        return _FakeResponse(204)

    monkeypatch.setattr(httpx.Client, "post", _post)

    ok = notify_license_purchased(
        jti="jti_purchase_1",
        email="buyer@x.co",
        tier="team",
        seat_count=5,
    )
    assert ok is True
    assert len(captured) == 1
    embed = captured[0]["payload"]["embeds"][0]
    assert "License purchased" in embed["title"]
    assert "buyer@x.co" in embed["description"]
    field_names = {f["name"] for f in embed["fields"]}
    assert "JTI" in field_names
    assert "Tier" in field_names
    assert "Seats" in field_names


def test_refund_posts_embed(monkeypatch):
    monkeypatch.setattr(
        settings, "discord_webhook_url", "https://discord.com/api/webhooks/test"
    )
    captured: list[dict] = []

    def _post(self, url, json=None):
        captured.append({"url": url, "payload": json})
        return _FakeResponse(204)

    monkeypatch.setattr(httpx.Client, "post", _post)

    ok = notify_refund(jti="jti_refund_a", reason="stripe_refund")
    assert ok is True
    embed = captured[0]["payload"]["embeds"][0]
    assert "Refund" in embed["title"]
    assert "stripe_refund" in embed["fields"][0]["value"]


def test_health_alert_swallows_network_error(monkeypatch):
    monkeypatch.setattr(
        settings, "discord_webhook_url", "https://discord.com/api/webhooks/test"
    )

    def _post(self, url, json=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.Client, "post", _post)

    # Must not raise — caller flow is critical-path
    ok = notify_health_alert(service="anthropic", error="rate_limited")
    assert ok is False
