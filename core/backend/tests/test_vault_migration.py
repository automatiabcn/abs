"""Plaintext .env → vault migration testleri."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def vault_env(monkeypatch, tmp_path: Path):
    """Vault paths + .env'i tmp'e izole et + data_dir."""
    from app.config import settings

    monkeypatch.setattr(settings, "vault_key_path", str(tmp_path / "age.key"))
    monkeypatch.setattr(settings, "vault_secrets_path", str(tmp_path / "secrets.yaml"))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    return {"tmp": tmp_path, "env": env_file}


def test_migration_skipped_when_no_vault(vault_env, monkeypatch):
    """Master key missing → migration 0, .env unchanged."""
    import app.vault.runner as runner_mod
    from app.vault.migration import migrate_plaintext_env_to_vault

    monkeypatch.setattr(runner_mod, "sops_available", lambda: False)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: False)

    vault_env["env"].write_text(
        "ABS_ANTHROPIC_API_KEY=sk-ant-leaktest\nABS_DATABASE_URL=sqlite:///x.db\n",
        encoding="utf-8",
    )
    n = migrate_plaintext_env_to_vault(env_path=str(vault_env["env"]))
    assert n == 0
    content = vault_env["env"].read_text(encoding="utf-8")
    assert "ABS_ANTHROPIC_API_KEY=sk-ant-leaktest" in content


def test_migration_moves_plaintext_to_vault(vault_env, monkeypatch):
    """sops + master key + plaintext .env → moves to vault, deletes from .env."""
    import app.vault.runner as runner_mod
    from app.vault.migration import migrate_plaintext_env_to_vault

    fake_store: dict[str, str] = {}

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: True)
    monkeypatch.setattr(runner_mod, "decrypt_all", lambda: dict(fake_store))

    def fake_write(key, value):
        fake_store[key] = value

    monkeypatch.setattr(runner_mod, "write_secret", fake_write)

    vault_env["env"].write_text(
        (
            "ABS_DATABASE_URL=sqlite:///x.db\n"
            "ABS_ANTHROPIC_API_KEY=sk-ant-test123\n"
            "ABS_GROQ_API_KEY=gsk_dummy\n"
            "ABS_DOMAIN=abs.local\n"
        ),
        encoding="utf-8",
    )
    n = migrate_plaintext_env_to_vault(env_path=str(vault_env["env"]))
    assert n == 2
    assert fake_store["anthropic_api_key"] == "sk-ant-test123"
    assert fake_store["groq_api_key"] == "gsk_dummy"
    rest = vault_env["env"].read_text(encoding="utf-8")
    # API key'ler silindi
    assert "ABS_ANTHROPIC_API_KEY" not in rest
    assert "ABS_GROQ_API_KEY" not in rest
    # API olmayanlar duruyor
    assert "ABS_DATABASE_URL" in rest
    assert "ABS_DOMAIN" in rest
    # Audit log written
    audit_path = Path(vault_env["tmp"]) / "vault_audit.jsonl"
    assert audit_path.is_file()
    text = audit_path.read_text(encoding="utf-8")
    assert "anthropic_api_key" in text
    # Cleartext value YAZILMADI
    assert "sk-ant-test123" not in text
    assert "gsk_dummy" not in text


def test_migration_idempotent(vault_env, monkeypatch):
    """Call twice → 0 migrated on 2nd call (.env already clean)."""
    import app.vault.runner as runner_mod
    from app.vault.migration import migrate_plaintext_env_to_vault

    fake_store: dict[str, str] = {}

    monkeypatch.setattr(runner_mod, "sops_available", lambda: True)
    monkeypatch.setattr(runner_mod, "master_key_exists", lambda: True)
    monkeypatch.setattr(runner_mod, "decrypt_all", lambda: dict(fake_store))
    monkeypatch.setattr(
        runner_mod, "write_secret", lambda k, v: fake_store.update({k: v})
    )

    vault_env["env"].write_text("ABS_ANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
    n1 = migrate_plaintext_env_to_vault(env_path=str(vault_env["env"]))
    assert n1 == 1
    n2 = migrate_plaintext_env_to_vault(env_path=str(vault_env["env"]))
    assert n2 == 0  # .env temiz, migrate edilecek bir şey yok
