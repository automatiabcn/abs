"""033 Modul A — Demo mode toggle + middleware header + status endpoint."""

from __future__ import annotations

from app.config import settings


def test_demo_mode_default_off(client):
    r = client.get("/v1/demo-mode/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["seed_version"]


def test_demo_mode_status_reports_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "provider_mock", True)
    r = client.get("/v1/demo-mode/status")
    assert r.json()["enabled"] is True
    assert r.json()["mock_providers"] is True


def test_demo_mode_middleware_sets_response_header(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers.get("X-ABS-Demo-Mode") == "true"
    assert "X-ABS-Demo-Seed-Version" in r.headers


def test_demo_mode_middleware_off_does_not_set_header(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    r = client.get("/healthz")
    assert "X-ABS-Demo-Mode" not in r.headers
