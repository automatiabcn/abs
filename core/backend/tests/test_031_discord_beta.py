"""031 Modul F — Discord beta-flow notifications (mocked transport)."""

from __future__ import annotations

from app.config import settings
from app.integrations import discord_webhook as dw


def test_notify_beta_request_noop_when_url_empty(monkeypatch):
    monkeypatch.setattr(settings, "discord_webhook_url", "")
    assert dw.notify_beta_request(email="x@x.com", name="X", use_case="trial") is False


def test_notify_beta_approved_payload(monkeypatch):
    monkeypatch.setattr(
        settings, "discord_webhook_url", "https://discord.example/hook/123"
    )
    captured: dict = {}

    def fake_post(embed: dict) -> bool:
        captured["embed"] = embed
        return True

    monkeypatch.setattr(dw, "_post", fake_post)
    ok = dw.notify_beta_approved(
        license_jti="jti_abcdef0123456789", email="alice@example.com"
    )
    assert ok is True
    embed = captured["embed"]
    assert "Beta license issued" in embed["title"]
    assert "alice@example.com" in embed["description"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["Tier"] == "beta"
    # JTI truncated to 16 chars for display
    assert "jti_abcdef012345" in fields["JTI"]


def test_notify_milestone_payload_includes_metric(monkeypatch):
    monkeypatch.setattr(
        settings, "discord_webhook_url", "https://discord.example/hook/123"
    )
    captured: dict = {}

    def fake_post(embed: dict) -> bool:
        captured["embed"] = embed
        return True

    monkeypatch.setattr(dw, "_post", fake_post)
    ok = dw.notify_milestone(metric="10 beta signups", value=10)
    assert ok is True
    assert "10 beta signups" in captured["embed"]["description"]
    assert any(f["value"] == "10" for f in captured["embed"]["fields"])
