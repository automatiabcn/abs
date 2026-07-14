"""Vault sops/age subprocess wrapper testleri.

If real binaries are installed, roundtrip + recipient tests run.
Otherwise bypass with pytest.skip.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REAL_BINARY = bool(shutil.which("sops")) and bool(shutil.which("age"))


@pytest.fixture
def vault_paths(monkeypatch, tmp_path: Path):
    """vault_key_path + vault_secrets_path tmp dizine, default sops_available off."""
    from app.config import settings

    key_path = tmp_path / "age.key"
    secrets_path = tmp_path / "secrets.yaml"
    monkeypatch.setattr(settings, "vault_key_path", str(key_path))
    monkeypatch.setattr(settings, "vault_secrets_path", str(secrets_path))
    return {"key": key_path, "secrets": secrets_path, "tmp": tmp_path}


def test_sops_available_false_when_binary_missing(monkeypatch):
    import app.vault.runner as runner_mod

    monkeypatch.setattr(runner_mod.shutil, "which", lambda _name: None)
    assert runner_mod.sops_available() is False


def test_decrypt_all_returns_empty_when_secrets_yaml_missing(vault_paths, monkeypatch):
    """sops binary mocked + master key mocked + secrets.yaml missing → {}"""
    import app.vault.runner as runner_mod

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    # master key dosyasi olarak gecici dummy yaz
    vault_paths["key"].write_text("# public key: age1mock\nDUMMY", encoding="utf-8")

    assert runner_mod.decrypt_all() == {}


def test_decrypt_raises_when_master_key_missing(vault_paths, monkeypatch):
    import app.vault.runner as runner_mod
    from app.vault.runner import VaultError

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    # key file missing
    with pytest.raises(VaultError) as exc:
        runner_mod.decrypt_all()
    assert exc.value.transient is False


def test_encrypt_subprocess_fail_raises_non_transient(vault_paths, monkeypatch):
    import app.vault.runner as runner_mod
    from app.vault.runner import VaultError

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    vault_paths["key"].write_text("# public key: age1mock\nDUMMY", encoding="utf-8")

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="mock fail")

    monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)
    with pytest.raises(VaultError) as exc:
        runner_mod.encrypt_all({"foo": "bar"})
    assert exc.value.transient is False


@pytest.mark.skipif(not REAL_BINARY, reason="sops/age binary not installed")
def test_encrypt_decrypt_roundtrip(vault_paths):
    """Real binary roundtrip — age-keygen + encrypt + decrypt should be equal."""
    import app.vault.runner as runner_mod

    # Create master key
    subprocess.run(
        ["age-keygen", "-o", str(vault_paths["key"])],
        check=True,
        capture_output=True,
        text=True,
    )

    runner_mod.encrypt_all(
        {"groq_api_key": "gsk_test", "anthropic_api_key": "sk-ant-test"}
    )
    decrypted = runner_mod.decrypt_all()
    assert decrypted == {"groq_api_key": "gsk_test", "anthropic_api_key": "sk-ant-test"}


@pytest.mark.skipif(not REAL_BINARY, reason="sops/age binary not installed")
def test_write_secret_upserts(vault_paths):
    """Real binary write_secret → tek key upsert."""
    import app.vault.runner as runner_mod

    subprocess.run(
        ["age-keygen", "-o", str(vault_paths["key"])],
        check=True,
        capture_output=True,
        text=True,
    )
    runner_mod.encrypt_all({})
    runner_mod.write_secret("foo", "bar")
    assert runner_mod.decrypt_all() == {"foo": "bar"}
    runner_mod.write_secret("foo", "baz")  # upsert
    assert runner_mod.decrypt_all() == {"foo": "baz"}
