# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""BUG-38 — FastMCP host whitelist resolves to localhost + customer
domain + sslip.io + ABS_MCP_ALLOWED_HOSTS env extras.

We test the helper functions only — module reload would re-create the
FastMCP instance after every test, leaving the global tool registry
empty for downstream tests in the same process.
"""

from __future__ import annotations

from app.mcp import server as mcp_server_mod


def test_resolve_allowed_hosts_includes_localhost(monkeypatch):
    monkeypatch.delenv("ABS_MCP_ALLOWED_HOSTS", raising=False)
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert "127.0.0.1" in hosts
    assert "localhost" in hosts
    assert "[::1]" in hosts


def test_resolve_allowed_hosts_includes_sslip_pilot(monkeypatch):
    monkeypatch.delenv("ABS_MCP_ALLOWED_HOSTS", raising=False)
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert "168.119.104.24.sslip.io" in hosts
    assert "168.119.104.24.sslip.io:*" in hosts


def test_extra_env_hosts_appended(monkeypatch):
    monkeypatch.setenv("ABS_MCP_ALLOWED_HOSTS", "abs.example.com,foo.bar")
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert "abs.example.com" in hosts
    assert "abs.example.com:*" in hosts
    assert "foo.bar" in hosts


def test_wildcard_short_circuits(monkeypatch):
    monkeypatch.setenv("ABS_MCP_ALLOWED_HOSTS", "*")
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert hosts == ["*"]
    sec = mcp_server_mod._build_security()
    assert sec is not None
    assert sec.enable_dns_rebinding_protection is False


def test_security_settings_has_origins(monkeypatch):
    monkeypatch.setenv("ABS_MCP_ALLOWED_HOSTS", "abs.example.com")
    sec = mcp_server_mod._build_security()
    assert sec is not None
    assert sec.enable_dns_rebinding_protection is True
    assert "abs.example.com" in sec.allowed_hosts
    assert "https://abs.example.com" in sec.allowed_origins
    assert "http://abs.example.com" in sec.allowed_origins


def test_settings_domain_added_when_non_default(monkeypatch):
    monkeypatch.delenv("ABS_MCP_ALLOWED_HOSTS", raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "domain", "abs.customer.tld")
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert "abs.customer.tld" in hosts
    assert "abs.customer.tld:*" in hosts


def test_settings_domain_default_skipped(monkeypatch):
    monkeypatch.delenv("ABS_MCP_ALLOWED_HOSTS", raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "domain", "abs.local")
    hosts = mcp_server_mod._resolve_allowed_hosts()
    assert "abs.local" not in hosts
