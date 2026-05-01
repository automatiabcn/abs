"""014 — Provider health monitor testleri (provider.call mock'lu)."""

from __future__ import annotations

import pytest

from app.providers.schemas import ProviderError, ProviderResponse


@pytest.mark.asyncio
async def test_snapshot_empty_initially():
    from app.health.monitor import HealthMonitor

    h = HealthMonitor()
    assert h.snapshot() == []


@pytest.mark.asyncio
async def test_ping_one_unknown_when_no_credentials(monkeypatch):
    """Provider key yokken state="unknown" + last_error mesajı."""
    import app.health.monitor as monitor_mod
    from app.health.monitor import HealthMonitor

    monkeypatch.setattr(monitor_mod, "_provider_has_credentials", lambda _n: False)
    h = HealthMonitor()
    result = await h._ping_one("groq")
    assert result.state == "unknown"
    assert result.last_error == "no credentials configured"


@pytest.mark.asyncio
async def test_ping_one_ok_when_provider_succeeds(monkeypatch):
    import app.health.monitor as monitor_mod
    from app.health.monitor import HealthMonitor

    monkeypatch.setattr(monitor_mod, "_provider_has_credentials", lambda _n: True)

    class FakeProvider:
        async def call(self, prompt, **kwargs):
            return ProviderResponse(
                text="ok", model="m", provider="groq", elapsed_ms=42
            )

    monkeypatch.setattr(
        monitor_mod, "get_registry", lambda: {"groq": FakeProvider()}
    )
    h = HealthMonitor()
    result = await h._ping_one("groq")
    assert result.state == "ok"
    assert result.latency_ms >= 0
    assert result.last_error is None
    assert result.consecutive_failures == 0


@pytest.mark.asyncio
async def test_ping_one_down_after_2_failures(monkeypatch):
    import app.health.monitor as monitor_mod
    from app.health.monitor import HealthMonitor

    monkeypatch.setattr(monitor_mod, "_provider_has_credentials", lambda _n: True)

    class FailingProvider:
        async def call(self, prompt, **kwargs):
            raise ProviderError("fake fail", provider="groq", transient=True)

    monkeypatch.setattr(
        monitor_mod, "get_registry", lambda: {"groq": FailingProvider()}
    )
    h = HealthMonitor()
    r1 = await h._ping_one("groq")
    assert r1.state == "warn"
    assert r1.consecutive_failures == 1
    r2 = await h._ping_one("groq")
    assert r2.state == "down"
    assert r2.consecutive_failures == 2


@pytest.mark.asyncio
async def test_snapshot_returns_sorted_dicts(monkeypatch):
    import app.health.monitor as monitor_mod
    from app.health.monitor import HealthMonitor

    monkeypatch.setattr(monitor_mod, "_provider_has_credentials", lambda _n: False)
    h = HealthMonitor()
    await h._ping_one("groq")
    await h._ping_one("anthropic")
    snap = h.snapshot()
    assert len(snap) == 2
    # alphabetically sorted by provider
    assert snap[0]["name"] == "Anthropic"
    assert snap[1]["name"] == "Groq"
    for entry in snap:
        assert {"name", "state", "latency_ms"} <= entry.keys()


def test_stream_orchestrator_uses_real_monitor(monkeypatch):
    """SSE _build_orchestrator artık random değil, monitor.snapshot() kullanır."""
    from app.api import stream as stream_mod
    from app.health.monitor import HealthMonitor

    fresh = HealthMonitor()
    monkeypatch.setattr(stream_mod, "_PROVIDERS", ["Groq", "Anthropic"])

    # fresh monitor boş → fallback unknown listesi
    import app.health.monitor as monitor_mod

    monkeypatch.setattr(monitor_mod, "monitor", fresh)
    payload = stream_mod._build_orchestrator()
    assert "providers" in payload
    assert all(p["state"] == "unknown" for p in payload["providers"])
    # judge placeholder
    assert payload["judge"]["score"] is None
    assert "Judge" in payload["judge"]["summary"]
