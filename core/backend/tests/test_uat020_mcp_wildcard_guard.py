"""ABS_MCP_ALLOWED_HOSTS='*' is forbidden in prod."""

from __future__ import annotations

import importlib
import os

import pytest

from app.config import settings


def _reload_mcp_server():
    import app.mcp.server as srv

    return importlib.reload(srv)


@pytest.fixture(autouse=True)
def _restore_mcp_server():
    """Put the module object back the way we found it.

    These tests reload `app.mcp.server` on purpose — that is the only way to
    exercise a boot guard that fires at import time. The catch is that the module
    builds `mcp_server = FastMCP(...)` at import, and the tools are registered
    onto *that instance* later, by `register_all_tools()` at app startup. A reload
    therefore swaps in a brand-new, empty server, and every later test that counts
    the registered tools counts zero — including the one asserting we still ship
    122 of them. Which tests broke depended on the collection order, which is why
    this went unseen.

    Two things do not fix it. Reloading the module *back* just builds a third
    empty instance. And putting the module back into `sys.modules` is a no-op,
    because `importlib.reload` does not create a new module object — it re-runs
    the code inside the existing one. The instance holding the tools is what has
    to be saved and put back.
    """
    import app.mcp.server as module

    populated = module.mcp_server
    yield
    os.environ.pop("ABS_MCP_ALLOWED_HOSTS", None)
    module.mcp_server = populated


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
