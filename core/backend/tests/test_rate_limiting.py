"""028 Modul G — Rate limiting (slowapi)."""

from __future__ import annotations

from app.middleware import rate_limit as rate_limit_module


def test_breach_count_starts_at_zero(monkeypatch):
    monkeypatch.setattr(rate_limit_module, "_breach_timestamps", [], raising=False)
    assert rate_limit_module.breach_count_24h() == 0


def test_record_breach_increments_counter(monkeypatch):
    monkeypatch.setattr(rate_limit_module, "_breach_timestamps", [], raising=False)
    rate_limit_module.record_breach()
    rate_limit_module.record_breach()
    rate_limit_module.record_breach()
    assert rate_limit_module.breach_count_24h() == 3


def test_breach_count_drops_old_entries(monkeypatch):
    """Entries older than 24h are dropped on next record."""
    import time as _t

    monkeypatch.setattr(rate_limit_module, "_breach_timestamps", [], raising=False)
    # Inject a fake-old timestamp directly
    rate_limit_module._breach_timestamps.append(_t.time() - 86400 - 1000)
    assert rate_limit_module.breach_count_24h() == 0  # already filtered

    rate_limit_module.record_breach()  # this resets buffer to recent only
    assert rate_limit_module.breach_count_24h() == 1


def test_limiter_singleton_exists():
    assert rate_limit_module.limiter is not None
    assert hasattr(rate_limit_module.limiter, "limit")


def test_install_rate_limit_idempotent_when_disabled(monkeypatch):
    """Disabling via setting → no-op."""
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    class _StubApp:
        state = type("S", (), {})()
        added: list = []

        def add_exception_handler(self, *a, **kw):
            self.added.append(("handler", a, kw))

        def add_middleware(self, *a, **kw):
            self.added.append(("middleware", a, kw))

    app = _StubApp()
    rate_limit_module.install_rate_limit(app)
    assert app.added == []  # nothing registered when disabled


def test_checkout_rate_limit_returns_429_after_threshold(client, monkeypatch):
    """11th request within 1 minute should be rate-limited."""
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "")

    # Reset the slowapi in-memory storage so tests don't leak between runs
    try:
        rate_limit_module.limiter._storage.reset()
    except Exception:
        pass

    saw_429 = False
    for _ in range(15):
        r = client.post(
            "/v1/checkout/create-session",
            json={"sku": "self-host", "customer_email": "rl@x.co"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
        if r.status_code == 429:
            saw_429 = True
            assert "Retry-After" in r.headers
            break
    assert saw_429, "Expected 429 within 15 requests on a 10/min limit"
