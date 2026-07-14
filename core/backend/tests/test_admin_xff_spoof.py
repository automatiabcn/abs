"""Auth/session round — admin /v1/admin/login X-Forwarded-For spoofing.

Regression for the bypass where ``app.api.admin.auth._client_ip`` blindly
trusted the client-supplied ``X-Forwarded-For`` header. That let an untrusted
caller:

  1. defeat ``admin_ip_whitelist`` by claiming a whitelisted IP, and
  2. reset the per-IP brute-force lockout on every request by rotating the
     header (``/v1/admin/login`` has no slowapi decorator — the in-memory
     ``_too_many_failures`` bucket is its only throttle).

The fix routes ``_client_ip`` through the trusted-proxy gate: XFF is
honoured only when the immediate hop is in ``ABS_TRUSTED_PROXIES``. TestClient's
socket host is ``testclient`` and is deliberately NOT trusted in these tests, so
the header is ignored — exactly the production posture for a direct/origin hit.
"""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _set_password(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )


@pytest.fixture(autouse=True)
def _reset_failures():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    # Default posture: the immediate hop (testclient) is untrusted, so a
    # client-set X-Forwarded-For must be ignored.
    yield
    a._reset_state_for_tests()


def test_xff_cannot_spoof_into_ip_whitelist(client, monkeypatch):
    """Untrusted hop claiming a whitelisted IP via XFF must be REJECTED."""
    _set_password(monkeypatch, "s3cret")
    monkeypatch.setattr(settings, "admin_ip_whitelist", "10.0.0.1")
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1,::1")  # not testclient
    r = client.post(
        "/v1/admin/login",
        json={"password": "s3cret"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    # Pre-fix: 200 (XFF honoured → whitelist bypassed). Post-fix: 403.
    assert r.status_code == 403


def test_xff_rotation_cannot_evade_bruteforce_lockout(client, monkeypatch):
    """Rotating X-Forwarded-For on each attempt must NOT reset the lockout
    bucket: all attempts key to the same real socket IP, so the 6th still 429s.
    """
    _set_password(monkeypatch, "s3cret")
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1,::1")  # not testclient
    for i in range(5):
        r = client.post(
            "/v1/admin/login",
            json={"password": "WRONG"},
            headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
        )
        assert r.status_code == 401, f"attempt {i} should be a plain auth failure"
    # 6th attempt with yet another fresh spoofed IP — pre-fix this resets the
    # bucket (still 401 and brute force continues); post-fix it is throttled.
    r = client.post(
        "/v1/admin/login",
        json={"password": "s3cret"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert r.status_code == 429


def test_trusted_proxy_xff_still_honoured_for_whitelist(client, monkeypatch):
    """Positive path: when the immediate hop IS trusted, the forwarded client
    IP is used for the whitelist (real reverse-proxy deployment)."""
    _set_password(monkeypatch, "s3cret")
    monkeypatch.setattr(settings, "admin_ip_whitelist", "10.0.0.1")
    monkeypatch.setattr(settings, "trusted_proxies", "testclient,127.0.0.1,::1")
    r = client.post(
        "/v1/admin/login",
        json={"password": "s3cret"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert r.status_code == 200
