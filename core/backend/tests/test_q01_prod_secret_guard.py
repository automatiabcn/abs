"""T-Q01 — production-secret leak guard tests."""

from __future__ import annotations

import pytest

from app.config import (
    Settings,
    assert_production_safe,
    validate_production_secrets,
)


def _dev_settings() -> Settings:
    """Fresh Settings instance with all default dev-insecure values."""
    return Settings()


def test_dev_env_never_raises() -> None:
    s = _dev_settings()
    assert s.env == "dev"
    assert_production_safe(s)  # must not raise


def test_validator_lists_every_dev_default_in_dev_env() -> None:
    leaked = validate_production_secrets(_dev_settings())
    assert {
        "unsubscribe_jwt_secret",
        "admin_token",
        "audit_ip_salt",
        "delete_confirm_jwt_secret",
        "beta_admin_token",
        "admin_jwt_secret",
        "session_secret",
        "admin_password_bootstrap",
        "vault_audit_hmac_secret",
    } <= set(leaked)


def test_prod_env_with_dev_defaults_raises() -> None:
    s = _dev_settings()
    s.env = "prod"
    with pytest.raises(RuntimeError) as excinfo:
        assert_production_safe(s)
    msg = str(excinfo.value)
    assert "ABS refusing to boot" in msg
    assert "session_secret" in msg
    assert "admin_token" in msg


def test_prod_env_with_real_secrets_passes() -> None:
    s = _dev_settings()
    s.env = "prod"
    s.unsubscribe_jwt_secret = "real-unsub-token"
    s.admin_token = "real-admin"
    s.audit_ip_salt = "real-salt"
    s.delete_confirm_jwt_secret = "real-delete"
    s.beta_admin_token = "real-beta"
    s.admin_jwt_secret = "real-admin-jwt"
    s.session_secret = "real-session"
    s.admin_password_bootstrap = "real-bootstrap"
    s.vault_audit_hmac_secret = "real-vault"
    s.neo4j_password = "real-neo4j-password"  # Sprint 2I #13
    leaked = validate_production_secrets(s)
    assert leaked == []
    assert_production_safe(s)  # must not raise
