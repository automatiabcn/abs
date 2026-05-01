"""028 Modul A — Slack signing verify (HMAC + replay window)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.config import settings
from app.integrations.slack_signing import verify_slack_signature


_SECRET = "8f742231b10e8888abcd99b1ee" + "0" * 50  # 64 char dummy


def _sign(secret: str, ts: str, body: bytes) -> str:
    base = b"v0:" + ts.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def test_signature_valid_passes():
    ts = str(int(time.time()))
    body = b'{"event": "test"}'
    sig = _sign(_SECRET, ts, body)
    ok, reason = verify_slack_signature(
        signing_secret=_SECRET, timestamp=ts, body=body, signature=sig
    )
    assert ok is True
    assert reason == ""


def test_signature_mismatch_rejected():
    ts = str(int(time.time()))
    body = b'{"event": "test"}'
    bad_sig = "v0=" + "0" * 64
    ok, reason = verify_slack_signature(
        signing_secret=_SECRET, timestamp=ts, body=body, signature=bad_sig
    )
    assert ok is False
    assert reason == "signature_mismatch"


def test_timestamp_expired_rejected():
    """Timestamp older than 5 minutes → replay attack guard."""
    old_ts = str(int(time.time()) - 600)  # 10 min ago
    body = b'{"event": "old"}'
    sig = _sign(_SECRET, old_ts, body)
    ok, reason = verify_slack_signature(
        signing_secret=_SECRET, timestamp=old_ts, body=body, signature=sig
    )
    assert ok is False
    assert reason == "timestamp_expired"


def test_empty_secret_fails_safe():
    ts = str(int(time.time()))
    ok, reason = verify_slack_signature(
        signing_secret="", timestamp=ts, body=b"{}", signature="v0=abc"
    )
    assert ok is False
    assert reason == "signing_secret_empty"


def test_url_verification_challenge_accepted(client, monkeypatch):
    monkeypatch.setattr(settings, "slack_signing_secret", _SECRET)
    ts = str(int(time.time()))
    body = json.dumps({"type": "url_verification", "challenge": "test_chal_123"}).encode()
    sig = _sign(_SECRET, ts, body)

    r = client.post(
        "/v1/integrations/slack/webhook",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["challenge"] == "test_chal_123"


def test_webhook_endpoint_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "slack_signing_secret", _SECRET)
    ts = str(int(time.time()))
    body = b'{"event": "x"}'
    r = client.post(
        "/v1/integrations/slack/webhook",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=" + "f" * 64,
        },
    )
    assert r.status_code == 401
    assert "signature" in r.json()["detail"].lower()
