"""`ConnectedSecret.encrypted_value` holds ciphertext when a key is configured.

It held base64 — always. The sops branch that was meant to be the real path
wrote somewhere else and then fell through to the same base64 return.
"""

from __future__ import annotations

import base64

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import ConnectedSecret
from app.db.session import get_engine
from app.smart_link import vault_secrets

_TOKEN = "ghs_a-token-worth-protecting-0123456789"


def _stored(key_name: str) -> str:
    with Session(get_engine()) as db:
        row = db.scalars(
            select(ConnectedSecret).where(ConnectedSecret.key_name == key_name)
        ).first()
        assert row is not None
        return row.encrypted_value


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setattr(
        settings, "provider_key_encryption_key", "a-test-encryption-secret"
    )


def test_the_stored_value_is_not_recoverable_without_the_key(with_key):
    vault_secrets.encrypt_secret(key_name="enc_t1", provider="github", value=_TOKEN)

    stored = _stored("enc_t1")

    assert stored.startswith("fernet:")
    assert _TOKEN not in stored
    assert base64.b64encode(_TOKEN.encode()).decode() not in stored


def test_it_reads_back_from_the_database_not_just_the_cache(with_key):
    vault_secrets.encrypt_secret(key_name="enc_t2", provider="github", value=_TOKEN)
    vault_secrets._CACHE.clear()

    assert vault_secrets.decrypt_secret("enc_t2") == _TOKEN


def test_rows_written_before_this_still_read(with_key):
    """Every existing row is `b64:`. Turning encryption on must not strand them."""
    legacy = "b64:" + base64.b64encode(_TOKEN.encode()).decode()
    with Session(get_engine()) as db:
        db.add(
            ConnectedSecret(
                key_name="enc_legacy", provider="slack", encrypted_value=legacy
            )
        )
        db.commit()
    vault_secrets._CACHE.clear()

    assert vault_secrets.decrypt_secret("enc_legacy") == _TOKEN


def test_without_a_key_dev_and_tests_keep_working(monkeypatch):
    monkeypatch.setattr(settings, "provider_key_encryption_key", "")
    vault_secrets.encrypt_secret(key_name="enc_t3", provider="github", value=_TOKEN)
    vault_secrets._CACHE.clear()

    assert _stored("enc_t3").startswith("b64:")
    assert vault_secrets.decrypt_secret("enc_t3") == _TOKEN
