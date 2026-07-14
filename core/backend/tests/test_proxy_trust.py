"""Slowapi X-Forwarded-For trust + proxy allowlist."""

from __future__ import annotations

from typing import Optional


class _FakeRequest:
    """Minimal Request-shaped object for the key_func unit test."""

    def __init__(self, client_host: str, xff: Optional[str] = None):
        self.client = type("c", (), {"host": client_host})()
        self.headers = {}
        if xff is not None:
            self.headers["x-forwarded-for"] = xff


def test_trusted_proxy_honours_x_forwarded_for(monkeypatch):
    """When the immediate hop is in ABS_TRUSTED_PROXIES we use the first
    IP from X-Forwarded-For for rate-limit keying."""
    from app.config import settings
    from app.middleware import rate_limit as rl

    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1,::1")
    req = _FakeRequest("127.0.0.1", "203.0.113.5")
    assert rl.client_ip_for_rate_limit(req) == "203.0.113.5"


def test_untrusted_proxy_falls_back_to_remote(monkeypatch):
    """An origin that is NOT in the allowlist cannot spoof its IP via
    X-Forwarded-For — we keep the raw socket address."""
    from app.config import settings
    from app.middleware import rate_limit as rl

    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")
    req = _FakeRequest("10.0.0.42", "203.0.113.5")
    assert rl.client_ip_for_rate_limit(req) == "10.0.0.42"


def test_multi_ip_xforwardedfor_takes_first(monkeypatch):
    """RFC 7239 chains list closest-to-original first; we pick that one
    and ignore the rest."""
    from app.config import settings
    from app.middleware import rate_limit as rl

    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")
    req = _FakeRequest("127.0.0.1", "198.51.100.7,  10.0.0.1,  203.0.113.1")
    assert rl.client_ip_for_rate_limit(req) == "198.51.100.7"
