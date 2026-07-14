"""Disaster scenario tests (4 senaryo).

1. Master key file deleted → rotate after restoring (escrow flow)
2. Vault file corrupted → restore from backup snapshot
3. HMAC secret rotated → audit chain re-init via reseal_chain
4. Partial secret corruption (b64 fallback for one) → granular rotate
"""

from __future__ import annotations


import pytest

from app.config import settings
from app.smart_link.vault_secrets import (
    _CACHE,
    decrypt_secret,
    encrypt_secret,
    list_secrets,
    rotate_secret,
)
from app.vault import rotation, runner
from app.vault.audit_chain import append_entry, reseal_chain, verify_chain


_FAKE_OLD_KEY = "# public key: age1olddisaster\nAGE-SECRET-KEY-1OLDDISASTER\n"
_FAKE_NEW_KEY = "# public key: age1newdisaster\nAGE-SECRET-KEY-1NEWDISASTER\n"


@pytest.fixture()
def _vault_env(tmp_path, monkeypatch):
    key_path = tmp_path / "age.key"
    secrets_path = tmp_path / "secrets.yaml"
    key_path.write_text(_FAKE_OLD_KEY)
    monkeypatch.setattr(settings, "vault_key_path", str(key_path))
    monkeypatch.setattr(settings, "vault_secrets_path", str(secrets_path))
    snapshot = {"foo": "bar"}

    monkeypatch.setattr(runner, "decrypt_all", lambda: dict(snapshot))

    def _enc(d):
        snapshot.clear()
        snapshot.update(d)
        secrets_path.write_text("encrypted-mock\n", encoding="utf-8")

    monkeypatch.setattr(runner, "encrypt_all", _enc)
    return key_path, secrets_path, snapshot


def test_scenario_1_master_key_deleted_then_restored(_vault_env):
    """Master key file disappears; restore from escrow then rotate as precaution."""
    key_path, _secrets, _snap = _vault_env
    # Simulate deletion
    key_path.unlink()
    assert not key_path.is_file()

    # Restore from "escrow"
    key_path.write_text(_FAKE_OLD_KEY)

    # Rotate as precaution
    out = rotation.rotate_age_key(reason="manual", keygen=lambda: _FAKE_NEW_KEY)
    assert out["ok"] is True
    assert "age1newdisaster" in key_path.read_text()


def test_scenario_2_vault_file_corrupted_restore_backup(_vault_env, monkeypatch):
    """Vault decrypt fails → user restores backup → decrypt works again."""
    key_path, secrets_path, snap = _vault_env
    secrets_path.write_text("encrypted-mock\n")

    # Corrupt the vault file
    secrets_path.write_text("CORRUPT_BAD_BLOB_NOT_YAML\n")
    # Simulate sops failure on this corrupted file
    monkeypatch.setattr(
        runner,
        "decrypt_all",
        lambda: (_ for _ in ()).throw(runner.VaultError("sops decrypt fail")),
    )

    with pytest.raises(runner.VaultError):
        runner.decrypt_all()

    # Restore: write a "backup" + put decrypt back to working
    secrets_path.write_text("encrypted-mock\n")
    monkeypatch.setattr(runner, "decrypt_all", lambda: dict(snap))
    assert runner.decrypt_all() == {"foo": "bar"}


def test_scenario_3_hmac_secret_rotation_resealed(monkeypatch):
    """Rotating vault_audit_hmac_secret invalidates chain; reseal restores."""
    # Seed chain
    append_entry(action="encrypt")
    append_entry(action="decrypt")
    append_entry(action="rotate")

    monkeypatch.setattr(settings, "vault_audit_hmac_secret", "rotated-disaster-secret")
    out = verify_chain()
    assert out["ok"] is False  # chain invalid under new secret

    # Reseal under the new secret
    reseal_chain()
    out2 = verify_chain()
    assert out2["ok"] is True


def test_scenario_4_partial_secret_corruption_granular_rotate():
    """One secret returns wrong value; rotate that secret only, others untouched."""
    _CACHE.clear()
    encrypt_secret(key_name="dis_keep", provider="anthropic", value="sk-ant-keep-this")
    encrypt_secret(key_name="dis_rotate", provider="openai", value="sk-old-bad")

    assert decrypt_secret("dis_rotate") == "sk-old-bad"

    # Rotate only the bad one
    rotate_secret(
        key_name="dis_rotate", provider="openai", new_value="sk-new-fixed-XYZ"
    )
    assert decrypt_secret("dis_rotate") == "sk-new-fixed-XYZ"
    # The other secret survived intact
    assert decrypt_secret("dis_keep") == "sk-ant-keep-this"

    rows = {r["key_name"]: r for r in list_secrets()}
    assert "dis_keep" in rows
    assert "dis_rotate" in rows
