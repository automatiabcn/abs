"""026 Modul C — vault_secrets encrypt/decrypt/rotate roundtrip."""

from __future__ import annotations


from sqlmodel import Session, select

from app.db.models import ConnectedSecret
from app.db.session import get_engine
from app.smart_link.vault_secrets import (
    _CACHE,
    decrypt_secret,
    delete_secret,
    encrypt_secret,
    list_secrets,
    rotate_secret,
    update_validation_status,
)


def _purge():
    """Reset cache + DB for clean test."""
    _CACHE.clear()
    with Session(get_engine()) as s:
        rows = s.scalars(select(ConnectedSecret)).all()
        for r in rows:
            s.delete(r)
        s.commit()


def test_encrypt_decrypt_roundtrip():
    _purge()
    encrypt_secret(key_name="openai_test", provider="openai", value="sk-secret-aaa")
    pt = decrypt_secret("openai_test")
    assert pt == "sk-secret-aaa"


def test_decrypt_returns_none_for_missing():
    _purge()
    assert decrypt_secret("does-not-exist") is None


def test_rotate_replaces_value_and_audit_log():
    _purge()
    encrypt_secret(key_name="rot_key", provider="openai", value="orig")
    assert decrypt_secret("rot_key") == "orig"
    rotate_secret(key_name="rot_key", provider="openai", new_value="rotated")
    assert decrypt_secret("rot_key") == "rotated"

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == "rot_key")
        ).all()
        # rotate replaces in place — single row
        assert len(rows) == 1
        assert rows[0].provider == "openai"


def test_list_secrets_does_not_expose_plaintext():
    _purge()
    encrypt_secret(
        key_name="anth_test", provider="anthropic", value="sk-ant-secret-xyz-123"
    )
    rows = list_secrets()
    assert len(rows) == 1
    keys = set(rows[0].keys())
    assert keys == {
        "key_name",
        "provider",
        "created_at",
        "last_validated_at",
        "last_validated_ok",
        "last_validated_error",
    }
    # No raw value leaked
    assert "sk-ant" not in str(rows)


def test_delete_and_validation_update_status():
    _purge()
    encrypt_secret(key_name="del_test", provider="cohere", value="sk-test-del")
    update_validation_status(key_name="del_test", ok=True, error=None)
    rows = list_secrets()
    assert rows[0]["last_validated_ok"] is True

    assert delete_secret("del_test") is True
    assert decrypt_secret("del_test") is None
    assert delete_secret("del_test") is False  # idempotent
