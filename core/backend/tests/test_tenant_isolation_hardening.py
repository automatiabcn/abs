"""Tenant-isolation hardening regression (repo audit round, Group B).

Defense-in-depth for multi-tenant deployments (the default single-tenant
deploy resolves everything to "default", so these guards are no-ops there).

1. Federated external-MCP proxy tools are registered in a GLOBAL FastMCP
   registry; a caller whose tenant differs from the tool's owning tenant must
   not be able to invoke it (and reach the upstream's credentials).
2. /v1/system/feature_usage must report the CALLER's tenant, not a hardcoded
   "default".
"""

from __future__ import annotations

import pytest

from app.mcp.context import set_mcp_caller


@pytest.fixture(autouse=True)
def _reset_caller():
    set_mcp_caller(None, None)
    yield
    set_mcp_caller(None, None)


async def test_federated_proxy_denies_cross_tenant_caller():
    from app.mcp.external import federation

    tool = federation._make_proxy_tool(
        ext_name="ext_acme__do",
        description="proxy",
        schema={"type": "object", "properties": {}},
        tenant_slug="acme",
        slug="acme-srv",
        orig="do",
    )

    # caller authenticated as a DIFFERENT tenant
    set_mcp_caller("other", "spy@other.com")
    out = await tool.run({})
    assert "cross-tenant access denied" in out[0].text


async def test_federated_proxy_allows_global_caller():
    """No tenant context (internal/admin token) → '_global' is allowed; the
    call proceeds to connection lookup (which returns 'unavailable' here since
    no server is configured) — i.e. it is NOT blocked by the tenant guard."""
    from app.mcp.external import federation

    tool = federation._make_proxy_tool(
        ext_name="ext_acme__do",
        description="proxy",
        schema={"type": "object", "properties": {}},
        tenant_slug="acme",
        slug="acme-srv",
        orig="do",
    )
    set_mcp_caller(None, None)  # -> "_global"
    out = await tool.run({})
    assert "cross-tenant access denied" not in out[0].text


def test_feature_usage_reports_caller_tenant(client, monkeypatch):
    from app.main import app
    from app.api.auth import current_admin
    from app.api.system import feature_usage as fu_endpoint

    monkeypatch.setattr(fu_endpoint, "_resolve_tenant", lambda email: "tenant-x")
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@tenant-x.com"}
    try:
        r = client.get("/v1/system/feature_usage")
        assert r.status_code == 200, r.text
        assert r.json()["tenant_slug"] == "tenant-x"
    finally:
        app.dependency_overrides.pop(current_admin, None)
