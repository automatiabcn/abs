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
    # "real-session" is twelve bytes. It is not the placeholder, so this test
    # passed — but the boot guard now also refuses signing secrets under 32
    # bytes, and twelve of them would be refused at a customer's door. A secret
    # a customer would really paste is 64 hex characters; use those.
    s = _dev_settings()
    s.env = "prod"
    s.unsubscribe_jwt_secret = "real-unsub-token".ljust(64, "0")
    s.admin_token = "real-admin".ljust(64, "0")
    s.audit_ip_salt = "real-salt".ljust(64, "0")
    s.delete_confirm_jwt_secret = "real-delete".ljust(64, "0")
    s.beta_admin_token = "real-beta".ljust(64, "0")
    s.admin_jwt_secret = "real-admin-jwt".ljust(64, "0")
    s.session_secret = "real-session".ljust(64, "0")
    s.admin_password_bootstrap = "real-bootstrap".ljust(64, "0")
    s.vault_audit_hmac_secret = "real-vault".ljust(64, "0")
    s.neo4j_password = "real-neo4j-password"
    leaked = validate_production_secrets(s)
    assert leaked == []
    assert_production_safe(s)  # must not raise
