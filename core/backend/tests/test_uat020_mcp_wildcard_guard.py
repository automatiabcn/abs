"""ABS_MCP_ALLOWED_HOSTS='*' is forbidden in prod."""

from __future__ import annotations

import importlib
import os

import pytest

from app.config import settings


def _reload_mcp_server():
    import app.mcp.server as srv

    return importlib.reload(srv)


def test_wildcard_allowed_hosts_in_prod_raises_systemexit(monkeypatch):
    """Module reload with env=prod + wildcard hosts must SystemExit at
    the module-level _build_security() call (boot guard, not lazy)."""
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setenv("ABS_MCP_ALLOWED_HOSTS", "*")

    with pytest.raises(SystemExit) as info:
        _reload_mcp_server()
    assert "wildcard" in str(info.value).lower() or "*" in str(info.value)


def test_wildcard_allowed_hosts_in_dev_still_allowed(monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setenv("ABS_MCP_ALLOWED_HOSTS", "*")

    srv = _reload_mcp_server()
    hosts = srv._resolve_allowed_hosts()
    assert hosts == ["*"]
    # Cleanup so a subsequent test starts fresh.
    os.environ.pop("ABS_MCP_ALLOWED_HOSTS", None)
