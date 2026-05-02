"""Q7 Phase B — Marketplace hardening edge cases.

Covers:
  1. install with cosign skip-mode → 201
  2. install rejected when verify_signature returns False → 403
  3. idempotent install (2nd call → already_installed)
  4. uninstall removes install record
  5. uninstall not found → 404
  6. cross-tenant isolation (admin tenant claim ≠ query tenant → 403)
  7. install all 5 catalog plugins → /installed returns 5 rows

Live docker tests (set ABS_DOCKER_LIVE=1) are skipped by default; the suite
relies on the install flow's graceful fallback when docker SDK is missing.
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest

# Public helpers / module under test ---------------------------------------
from app.api import marketplace as marketplace_module
from app.config import settings


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _login(client) -> None:
    # Q12-L19 Round 11 — TestClient `/auth/login` POST 307→/setup unless
    # setup_state.json `completed:true` is seeded by the autouse
    # `_autocomplete_setup_state` fixture in conftest. With that fixture,
    # bootstrap admin (admin@local/CHANGEME) authenticates via source 1
    # (DB) or source 2 (admin_credentials.json).
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _ensure_cosign_skip(monkeypatch) -> Iterator[None]:
    """Default: skip-mode ON so install isn't gated on a real cosign binary."""
    monkeypatch.setattr(settings, "cosign_skip", True)
    yield


@pytest.fixture(autouse=True)
def _isolated_install_store(tmp_path, monkeypatch) -> Iterator[None]:
    """Per-test isolated marketplace_installs.json under tmp_path.

    Q12-L19 Round 11 — also re-seed `setup_state.json` so the FirstRun
    middleware doesn't redirect /auth/login to /setup. The autouse
    `_autocomplete_setup_state` conftest fixture writes to the
    *session* data_dir; this fixture monkeypatches data_dir per-test,
    so the seed is missing in the new dir without an explicit re-write.
    """
    import json
    import time

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    state_path = tmp_path / "setup_state.json"
    state_path.write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": [
                    "admin",
                    "license",
                    "domain",
                    "anthropic",
                    "providers",
                    "test",
                ],
                "started_at": time.time(),
                "completed_at": time.time(),
                "data": {},
            }
        ),
        encoding="utf-8",
    )
    yield


# --------------------------------------------------------------------------
# 1) install with cosign skip → 201
# --------------------------------------------------------------------------


def test_install_with_cosign_skip(client) -> None:
    _login(client)
    r = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "installed"
    assert body["plugin_id"] == "slack-receiver"
    assert body["tenant"] == "default"
    # docker SDK is optional in CI → expect graceful no-sandbox path
    assert body["sandbox_status"] in {"installed_no_sandbox", "running"}


# --------------------------------------------------------------------------
# 2) signature invalid → 403
# --------------------------------------------------------------------------


def test_install_invalid_signature_rejected(client, monkeypatch) -> None:
    _login(client)

    from app.marketplace import cosign_verify

    monkeypatch.setattr(cosign_verify, "verify_signature", lambda *a, **kw: False)
    r = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "signature_invalid"


# --------------------------------------------------------------------------
# 3) idempotent install
# --------------------------------------------------------------------------


def test_idempotent_install(client) -> None:
    _login(client)
    r1 = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    # idempotent path must succeed (200) with already_installed marker
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_installed"


# --------------------------------------------------------------------------
# 4) uninstall removes the record
# --------------------------------------------------------------------------


def test_uninstall_removes_record(client) -> None:
    _login(client)
    client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "default"},
    )
    r = client.delete(
        "/v1/marketplace/uninstall/slack-receiver?tenant=default",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "uninstalled"
    assert body["plugin_id"] == "slack-receiver"

    listing = client.get("/v1/marketplace/installed?tenant=default")
    assert listing.status_code == 200
    assert listing.json()["installed"] == []


# --------------------------------------------------------------------------
# 5) uninstall non-existent → 404
# --------------------------------------------------------------------------


def test_uninstall_not_found(client) -> None:
    _login(client)
    r = client.delete(
        "/v1/marketplace/uninstall/slack-receiver?tenant=default",
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "not_installed"


# --------------------------------------------------------------------------
# 6) cross-tenant isolation
# --------------------------------------------------------------------------


def test_cross_tenant_isolation(client) -> None:
    """When the admin token carries tenant=A, a query for tenant=B → 403."""
    # FastAPI dependency override is the only reliable way to inject a
    # synthetic tenant claim — `current_admin` was bound at import time.
    from app.api.marketplace import current_admin as live_dep
    from app.main import app

    app.dependency_overrides[live_dep] = lambda: {
        "sub": "admin@local",
        "tenant": "tenant-a",
    }
    try:
        r = client.get("/v1/marketplace/installed?tenant=tenant-b")
        assert r.status_code == 403
        assert r.json()["detail"] == "cross_tenant_forbidden"

        # Same-tenant query should pass.
        r2 = client.get("/v1/marketplace/installed?tenant=tenant-a")
        assert r2.status_code == 200
    finally:
        app.dependency_overrides.pop(live_dep, None)


# --------------------------------------------------------------------------
# 7) install all 5 catalog plugins → list returns 5
# --------------------------------------------------------------------------


def test_install_5_plugins_then_list(client) -> None:
    _login(client)
    plugin_ids = [p["id"] for p in marketplace_module.PLUGIN_CATALOG]
    assert len(plugin_ids) == 5

    for pid in plugin_ids:
        r = client.post(
            "/v1/marketplace/install",
            json={"plugin_id": pid, "tenant": "default"},
        )
        assert r.status_code == 201, f"{pid}: {r.text}"

    r = client.get("/v1/marketplace/installed?tenant=default")
    assert r.status_code == 200
    rows = r.json()["installed"]
    assert len(rows) == 5
    assert {row["plugin_id"] for row in rows} == set(plugin_ids)


# --------------------------------------------------------------------------
# Live docker-only smoke (skipped without ABS_DOCKER_LIVE=1)
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ABS_DOCKER_LIVE") != "1",
    reason="requires real docker daemon (set ABS_DOCKER_LIVE=1)",
)
def test_live_docker_launch_smoke() -> None:  # pragma: no cover — gated
    from app.marketplace.sandbox import PluginSandbox

    sandbox = PluginSandbox()
    out = sandbox.launch(
        "slack-receiver",
        "tenant-live",
        {"mem_mb": 64, "cpu_cores": 0.25},
    )
    assert out["status"] in {"running", "already_running"}
    sandbox.stop("slack-receiver", "tenant-live")
