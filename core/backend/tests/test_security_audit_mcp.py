"""028 Modul H — `security_audit` MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_security_audit_response_shape():
    from app.mcp.tools.security_tools import security_audit

    raw = asyncio.run(security_audit())
    out = json.loads(raw)
    for key in (
        "webhook_secrets",
        "oauth_active_states",
        "rate_limit_breaches_24h",
        "vault_audit",
        "tls_cert_expires_days",
        "overall_score",
    ):
        assert key in out, f"missing key: {key}"
    assert out["overall_score"] in {"ok", "warn", "danger"}


def test_security_audit_warns_when_secrets_missing(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    monkeypatch.setattr(settings, "slack_signing_secret", "")
    monkeypatch.setattr(settings, "github_app_webhook_secret", "")

    from app.mcp.tools.security_tools import security_audit

    out = json.loads(asyncio.run(security_audit()))
    assert out["webhook_secrets"]["stripe_set"] is False
    assert out["webhook_secrets"]["slack_set"] is False
    assert out["webhook_secrets"]["github_app_set"] is False
    # Multiple unset secrets → warn level
    assert out["overall_score"] in {"warn", "danger"}


def test_security_audit_records_breach_count(monkeypatch):
    from app.middleware import rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "_breach_timestamps", [], raising=False)
    rate_limit_module.record_breach()
    rate_limit_module.record_breach()

    from app.mcp.tools.security_tools import security_audit

    out = json.loads(asyncio.run(security_audit()))
    assert out["rate_limit_breaches_24h"] >= 2
