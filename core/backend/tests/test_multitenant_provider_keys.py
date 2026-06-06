"""Multi-tenant Phase 1 — provider key crypto + store + resolution order."""

from __future__ import annotations

import pytest

from app.config import settings
from app.multitenant import crypto
from app.multitenant import provider_keys as pk


# ── crypto ────────────────────────────────────────────────────────────────


def test_b64_fallback_roundtrip_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_key_encryption_key", "", raising=False)
    enc = crypto.encrypt_secret_value("sk-secret-123")
    assert enc.startswith("b64:")
    assert crypto.decrypt_secret_value(enc) == "sk-secret-123"


def test_fernet_roundtrip_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "provider_key_encryption_key", "unit-test-master", raising=False
    )
    enc = crypto.encrypt_secret_value("gsk_live_key")
    assert enc.startswith("fernet:")
    assert "gsk_live_key" not in enc  # actually encrypted
    assert crypto.decrypt_secret_value(enc) == "gsk_live_key"


def test_fernet_value_undecryptable_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "provider_key_encryption_key", "master-a", raising=False
    )
    enc = crypto.encrypt_secret_value("topsecret")
    monkeypatch.setattr(settings, "provider_key_encryption_key", "", raising=False)
    with pytest.raises(ValueError):
        crypto.decrypt_secret_value(enc)


# ── store + resolution ──────────────────────────────────────────────────────


def test_set_and_resolve_user_key() -> None:
    pk.set_provider_key(
        tenant_slug="t-user",
        owner_type=pk.OWNER_USER,
        owner_id="ahmet@x.com",
        provider="groq",
        value="user-key",
    )
    got = pk.resolve_provider_key(
        "groq", tenant_slug="t-user", user_subject="ahmet@x.com", include_global=False
    )
    assert got == "user-key"


def test_resolution_order_project_over_user_over_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = "t-order"
    monkeypatch.setattr(settings, "groq_api_key", "GLOBAL", raising=False)
    pk.set_provider_key(
        tenant_slug=t, owner_type=pk.OWNER_ORG, owner_id=t, provider="groq",
        value="ORG",
    )
    pk.set_provider_key(
        tenant_slug=t, owner_type=pk.OWNER_USER, owner_id="u@x.com", provider="groq",
        value="USER",
    )
    pk.set_provider_key(
        tenant_slug=t, owner_type=pk.OWNER_PROJECT, owner_id="proj1", provider="groq",
        value="PROJECT",
    )

    # All three contexts present → project wins.
    assert pk.resolve_provider_key(
        "groq", tenant_slug=t, project_slug="proj1", user_subject="u@x.com"
    ) == "PROJECT"
    # No project context → user wins.
    assert pk.resolve_provider_key(
        "groq", tenant_slug=t, user_subject="u@x.com"
    ) == "USER"
    # No project/user context → org wins.
    assert pk.resolve_provider_key("groq", tenant_slug=t) == "ORG"
    # Project context without a project-level key → falls back to user.
    assert pk.resolve_provider_key(
        "groq", tenant_slug=t, project_slug="other", user_subject="u@x.com"
    ) == "USER"


def test_resolution_falls_back_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "GLOBAL-KEY", raising=False)
    got = pk.resolve_provider_key(
        "groq", tenant_slug="t-empty", user_subject="nobody@x.com"
    )
    assert got == "GLOBAL-KEY"


def test_resolution_global_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "GLOBAL-KEY", raising=False)
    got = pk.resolve_provider_key(
        "groq", tenant_slug="t-empty2", include_global=False
    )
    assert got is None


def test_tenant_isolation_no_cross_tenant_resolution() -> None:
    pk.set_provider_key(
        tenant_slug="tenantA", owner_type=pk.OWNER_USER, owner_id="shared@x.com",
        provider="cohere", value="A-KEY",
    )
    # Same user id, different tenant → must NOT see tenant A's key.
    assert pk.resolve_provider_key(
        "cohere", tenant_slug="tenantB", user_subject="shared@x.com",
        include_global=False,
    ) is None
    assert pk.resolve_provider_key(
        "cohere", tenant_slug="tenantA", user_subject="shared@x.com",
        include_global=False,
    ) == "A-KEY"


def test_set_is_idempotent_upsert() -> None:
    pk.set_provider_key(
        tenant_slug="t-up", owner_type=pk.OWNER_ORG, owner_id="t-up",
        provider="gemini", value="v1",
    )
    pk.set_provider_key(
        tenant_slug="t-up", owner_type=pk.OWNER_ORG, owner_id="t-up",
        provider="gemini", value="v2",
    )
    assert pk.resolve_provider_key(
        "gemini", tenant_slug="t-up", include_global=False
    ) == "v2"


def test_delete_provider_key() -> None:
    pk.set_provider_key(
        tenant_slug="t-del", owner_type=pk.OWNER_ORG, owner_id="t-del",
        provider="cerebras", value="x",
    )
    assert pk.delete_provider_key(
        tenant_slug="t-del", owner_type=pk.OWNER_ORG, owner_id="t-del",
        provider="cerebras",
    ) is True
    assert pk.delete_provider_key(
        tenant_slug="t-del", owner_type=pk.OWNER_ORG, owner_id="t-del",
        provider="cerebras",
    ) is False


def test_list_provider_keys_has_no_plaintext() -> None:
    pk.set_provider_key(
        tenant_slug="t-list", owner_type=pk.OWNER_USER, owner_id="a@x.com",
        provider="groq", value="super-secret",
    )
    rows = pk.list_provider_keys(tenant_slug="t-list")
    assert rows and rows[0]["provider"] == "groq"
    blob = str(rows)
    assert "super-secret" not in blob
    assert "encrypted_value" not in blob


def test_invalid_owner_type_rejected() -> None:
    with pytest.raises(ValueError):
        pk.set_provider_key(
            tenant_slug="t", owner_type="robot", owner_id="x", provider="groq",
            value="k",
        )
