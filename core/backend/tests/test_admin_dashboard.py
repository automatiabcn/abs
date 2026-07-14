"""Aggregated dashboard endpoint + cache."""

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


def _login(client, monkeypatch) -> str:
    _set_password(monkeypatch, "s3cret")
    return client.post("/v1/admin/login", json={"password": "s3cret"}).json()["token"]


@pytest.fixture(autouse=True)
def _wipe_dashboard_cache():
    from app.api.admin.dashboard import reset_cache_for_tests
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_dashboard_requires_admin_bearer(client):
    r = client.get("/v1/admin/dashboard")
    assert r.status_code == 401


def test_dashboard_aggregates_5_sources(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("billing", "beta", "compliance", "security", "vault"):
        assert key in body, f"missing source: {key}"


def test_dashboard_returns_cached_on_second_call(client, monkeypatch):
    token = _login(client, monkeypatch)
    h = {"Authorization": f"Bearer {token}"}
    r1 = client.get("/v1/admin/dashboard", headers=h)
    r2 = client.get("/v1/admin/dashboard", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("cached") is True


def test_dashboard_refresh_param_bypasses_cache(client, monkeypatch):
    token = _login(client, monkeypatch)
    h = {"Authorization": f"Bearer {token}"}
    r1 = client.get("/v1/admin/dashboard", headers=h)
    assert r1.json().get("cached") is False
    r2 = client.get("/v1/admin/dashboard?refresh=true", headers=h)
    assert r2.status_code == 200
    assert r2.json().get("cached") is False


def test_dashboard_billing_summary_shape(client, monkeypatch):
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    billing = r.json()["billing"]
    for key in ("licenses_total", "licenses_active", "tier_breakdown"):
        assert key in billing


def test_dashboard_sources_emit_keys_the_panel_reads(client, monkeypatch):
    """3rd-eye audit regression — the /admin/dashboard panel cards read these
    exact keys. They previously read phantom keys (active_signups / soc2_score
    / findings_count / secrets_count) that NO producer emits, so four of six
    cards showed 0 / — on every render. Lock the producer→consumer contract so
    a future rename on either side fails loudly here instead of silently
    zeroing the dashboard.
    """
    token = _login(client, monkeypatch)
    body = client.get(
        "/v1/admin/dashboard?refresh=true",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # beta card → pending + approved
    assert "pending" in body["beta"] and "approved" in body["beta"]
    # compliance card → overall_status (ok|warn|gap)
    assert "overall_status" in body["compliance"]
    # security card → overall_score
    assert "overall_score" in body["security"]
    # vault card → total_entries
    assert "total_entries" in body["vault"]

    # the phantom keys must NOT be what we rely on (guard against reintroduction)
    assert "active_signups" not in body["beta"]
    assert "soc2_score" not in body["compliance"]


def test_dashboard_resilient_to_partial_source_failure(client, monkeypatch):
    """If one source raises, dashboard still returns 200 with empty default."""
    from app.mcp.tools import beta_tools

    async def boom():
        raise RuntimeError("simulated source failure")

    monkeypatch.setattr(beta_tools, "beta_metrics", boom)
    token = _login(client, monkeypatch)
    r = client.get(
        "/v1/admin/dashboard?refresh=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    # billing is local SQL, will still work
    assert "billing" in body
